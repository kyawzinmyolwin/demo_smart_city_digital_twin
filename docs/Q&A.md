# Q&A — demo & viva preparation

Prepared answers to likely questions about the Christchurch decision-support digital
twin. Each answer is traced to the real code and AWS resources so it can be defended.

---

## Q1. When I click "Start: Baseline — morning peak", what is the complete flow?

This traces the **cloud** path (the deployed demo). The same dashboard button also
drives the **local** `control_server.py` — the only differences are noted at the end.

### One-line summary
Browser → authenticated control API → a Lambda that tells the EC2 sim host (via SSM)
to run the baseline scenario → SUMO streams vehicle snapshots back up through the
WebSocket API → they fan out to the browser (live map) and are aggregated into
InfluxDB (history/compare).

### Step by step

**1. Browser — the click.**
The button was created from the preset list (`GET /scenarios`) when the panel loaded.
Clicking it calls `scnStart("baseline_am")`, which sends:
```
POST  <control-api>/start?scenario=baseline_am
Header: Authorization: Bearer <token>
```
The `scnFetch()` helper (in `intersection_map.html`) prepends the `?control=` API URL
and attaches the `?token=` bearer header.

**2. CORS preflight.**
Because it's a cross-origin POST with a custom `Authorization` header, the browser
first sends an `OPTIONS` preflight. The control HTTP API's CORS config answers it
(allowed origin/methods/headers). Preflight is **not** authorized.

**3. API Gateway (control HTTP API) → token authorizer.**
The `POST /start` route has a custom Lambda authorizer. API Gateway invokes the
**`control-authorizer`** Lambda, which constant-time-compares the bearer token against
its `CONTROL_TOKEN` env var and returns `{"isAuthorized": true}`. A wrong/missing token
→ **401**, and the flow stops here. (This is why the public dashboard is read-only
without the token.)

**4. API Gateway → `traffic-control` Lambda.**
With authorization granted, API Gateway proxies the request (payload v2) to the
**`traffic-control`** Lambda. The event has `routeKey = "POST /start"` and
`queryStringParameters = {scenario: "baseline_am"}`.

**5. `traffic-control` Lambda — validate, then command the sim host.**
(`infra/functions/traffic_control/handler.py`)
- Validates `"baseline_am"` is in the **preset allowlist** (`PRESETS`). Unknown → 400.
- `_sim_host_running()` → `ec2:DescribeInstances` filtered by `tag:Name =
  christchurch-digital-twin-prod-sim-host` + state `running`. None → **409 "sim host not
  running"**.
- Builds the scenario args from the preset (never from arbitrary input):
  `--real-time --speed 5 --jump-to 23400 --end 27000 --scenario-id baseline_am`.
- Sends an **SSM Run Command** (`ssm:SendCommand`, `AWS-RunShellScript`, targeted by
  the sim-host tag) whose shell body:
  ```
  cat > /etc/sumo-emitter.env <<'SUMOEOF'
  SCENARIO_ARGS=--real-time --speed 5 --jump-to 23400 --end 27000 --scenario-id baseline_am
  SUMOEOF
  systemctl restart sumo-emitter
  ```
- Records intent in **SSM Parameter Store** (`/christchurch-digital-twin/prod/sim-control/state`)
  so `GET /status` can report it.
- Returns `200 {"ok": true, "scenario": "baseline_am"}`.

**6. SSM → the EC2 sim host.**
The SSM agent on the box (outbound-only; no open ports) receives the command and runs
it as root: it rewrites `/etc/sumo-emitter.env` with the new `SCENARIO_ARGS` and does
`systemctl restart sumo-emitter`.

**7. The sim host runs the simulation.**
systemd restarts the `sumo-emitter` service, whose `ExecStart` (with `$SCENARIO_ARGS`
expanded from the env file) is:
```
python scripts/run_traci.py --no-gui --emit-interval 10 --emit-target "wss://<ws-api>/prod" \
        --real-time --speed 5 --jump-to 23400 --end 27000 --scenario-id baseline_am
```
`run_traci.py` launches headless SUMO via TraCI, jumps to sim time 23400 (06:30), and
steps in real time (×5). Every 10th tick it forwards a vehicle-state snapshot (tagged
`scenarioId = baseline_am`) to the cloud **WebSocket API Gateway** via the
`CloudForwarder` (`{"action":"sendmessage","data":{…}}`).

**8. Browser — connect to the live feed.**
After the POST resolves, `scnStart` shows "started… connecting", waits ~2.5 s, then
`connectWs()` opens a WebSocket to the `?ws=` URL (the WebSocket API Gateway). It also
starts polling `GET /status` every 3 s (which reads the Parameter Store state).

**9. Cloud data path — how vehicles appear and history fills.**
Each snapshot the sim host sends hits the **WebSocket API Gateway** (`sendmessage`) →
**`traffic-ingest`** Lambda, which:
- looks up connected browsers in the **DynamoDB connections table** and **fans the
  snapshot out** to them (`postToConnection`) — the browser draws the speed-coloured
  vehicles on the Leaflet map and updates the live Chart.js panels + sim clock; and
- async-invokes **`traffic-metrics`**, which runs `compute_tick_metrics` and writes the
  per-tick metrics to **InfluxDB Cloud** (tagged `simId` + `scenario_id`). That feeds
  the **History / Compare / Impact** panels via the **`traffic-replay`** Lambda.

### Compact sequence
```
click → scnFetch POST /start (Bearer token)
      → [CORS preflight] → control API Gateway
      → control-authorizer Lambda (token ok?)
      → traffic-control Lambda → EC2 DescribeInstances + SSM SendCommand + Parameter Store
      → SSM agent on sim host → rewrite env file → systemctl restart sumo-emitter
      → run_traci.py + SUMO (baseline, real-time) → emit snapshots
      → WebSocket API Gateway → traffic-ingest Lambda
            ├─ fan-out to browser WS → live vehicles + charts
            └─ traffic-metrics Lambda → InfluxDB Cloud → (replay) History/Compare/Impact
```

### Safety points (worth stating in the viva)
- The control endpoint is **token-authenticated** because starting a run triggers
  compute/cost.
- The command is composed **only from a fixed preset allowlist** (and, for a road
  block, a regex-validated edge id) — never from free-form input — so the SSM/shell
  command can't be turned into arbitrary execution.
- IAM is **least-privilege**: `ssm:SendCommand` is restricted to the sim host **by tag**.

### How the local path differs
With `?control=http://localhost:8799` (no token), the same button hits
`control_server.py` on the SUMO machine, which **spawns `run_traci.py` directly** (and
auto-starts `metrics_writer.py`) instead of going through API Gateway → SSM → EC2. The
HTTP contract (`/scenarios`, `/start`, `/stop`, `/status`, `/start_roadblock`) is
identical, which is why one dashboard panel drives both.

---

## Q2. We only have Baseline and Crash preset buttons. If the product owner / examiner asks for more scenario comparisons, how do we fulfil that?

**Key point:** the **Compare view compares any two `scenario_id`s that have data in
InfluxDB** — the preset buttons are just shortcuts for producing tagged runs. So "more
comparisons" means "more tagged runs". There are several ways, increasing in effort:

1. **Click-a-road closure (no code change, examiner-driven).** Click any road on the
   map → **Start road block** → a run that closes that edge. The examiner chooses the
   scenario live. *(Caveat: by default every road block is tagged `scenario_id =
   "roadblock"`, so two different closures aren't independently comparable — see the
   enhancement below.)*
2. **Compare any two existing runs (no change).** Every run is tagged and stored; enter
   any two `scenario_id`s in the Compare panel (e.g. `baseline_am` vs `roadworks`, the
   3rd preset). You are not limited to two scenarios.
3. **Add named preset buttons (small change + redeploy).** Add entries to the `PRESETS`
   registry — kept in **two** places: `scripts/control_server.py` (local — just restart)
   and `infra/functions/traffic_control/handler.py` (cloud — `terraform apply`
   repackages the Lambda). Each preset is a `scenario_id` + args: a different
   `--close-edge=<edge>@<window>` or an `--incident-file` (reduced-speed corridor or
   demand surge via `incidents.py`).
4. **Local CLI (maximum flexibility).** `run_traci.py --scenario-id <any> --close-edge …
   / --incident-file …` tags a run with any id, which then appears in Compare. The
   **cloud is deliberately preset-only** (no arbitrary args over the network) for safety.

**Recommended enhancement.** Tag each click-a-road closure with a **unique id per edge**
(`rb_<edge>`) so every road on the map becomes its own comparable scenario — giving the
examiner unlimited, live-chosen comparisons with no per-scenario code change. Plus a few
more preset buttons for variety (longer full-morning closure, reduced-speed corridor,
demand surge).

**Safety framing (for the viva):** arbitrary scenario definitions are never accepted over
the cloud control API — only a fixed preset allowlist plus a regex-validated edge id.
That is why the cloud path is preset-only while the local CLI is unrestricted.

---

## Q3. Why doesn't "Close live" work in the cloud demo?

**It is expected, not a bug — "Close live" is local-only by design.**

"Close live" (and its "Reopen road (resume)" toggle) injects a closure into the
**already-running** simulation by sending a control frame **up the live WebSocket** to
the emitter's inbound `ControlInbox` (the Inc 3 click-to-inject mechanism). That requires
a two-way channel between the browser and `run_traci.py`.

In the cloud that back-channel does not exist, for two reasons:

1. **No inbound server on the sim host.** The cloud sim host runs the emitter in
   forward-only mode — `run_traci.py ... --emit-target wss://…` with **no `--emit` /
   `--emit-host`** — so there is **no local WebSocket server and no `ControlInbox`**
   listening for control frames.
2. **The cloud live feed is one-way fan-out.** The emitter *dials out* and posts
   snapshots to the WebSocket API Gateway → `traffic-ingest` Lambda → fanned out to
   browsers. The browser is a **consumer** of that feed; there is no route for it to send
   a control frame back to that specific emitter.

So in the cloud there is nothing on the other end to receive "Close live".

**What to use in the cloud instead:** **Scenario control → "Start road block"** (click a
road → Start road block). That goes through the authenticated cloud control API and starts
a **fresh run with the edge closed from the start** — which does work in the cloud, and
still demonstrates incident impact via Compare / Impact report.

| Action | Local | Cloud |
|---|---|---|
| **Close live** — inject into the *running* sim; watch recovery on reopen | yes | no (by design) |
| **Start road block** — fresh run with the edge closed | yes | yes |

Documented in `CLAUDE.md` and the report's §11 limitations ("Cloud click-to-inject is
local-only"). A true cloud live-inject is a deferred larger build (see CHECKLIST planned
improvements).

---

## Q4. Why does the cloud pipeline use AWS Lambda, but the local pipeline doesn't?

**Key point: Lambda is AWS-managed serverless compute — it only exists on AWS. Locally,
the *same pure logic* runs inside an ordinary long-running process instead. The behaviour
is identical; only the host that runs it differs.**

The metrics step is the clearest example. The actual computation is one pure function,
`compute_tick_metrics` (`scripts/metrics.py`):

- **Cloud:** that function is the body of the **`traffic-metrics` Lambda** — the file is
  copied verbatim into `infra/functions/traffic_metrics/` and invoked per snapshot.
- **Local:** the **same** `compute_tick_metrics` is imported and called by
  `metrics_writer.py`, a long-running process that reads the WebSocket feed and writes to
  local InfluxDB.

So there is no duplicated or diverging logic — just two runtimes for one function.

### Why a different host in each environment

1. **Lambda is an AWS service; it can't run on a laptop.** Off-AWS there is no API
   Gateway or Lambda. You *could* emulate it (AWS SAM / LocalStack), but that is heavy
   tooling for no benefit in a self-contained dev/demo stack.
2. **Each model fits its environment.** In the cloud, an **event-driven, serverless**
   function is ideal: it **scales to zero** (near-zero idle cost — the whole stack is
   ~$1–2/month idle), auto-scales per message, and needs no server to manage — exactly
   right for a bursty pipeline on a student budget. Locally, the stack is already **one
   machine up via Docker Compose**, so a **plain long-running container process** is
   simpler: no API Gateway, no cold-start latency, no per-invoke overhead, nothing to
   emulate.
3. **The design deliberately separates pure logic from its runtime.** Because
   `compute_tick_metrics` is a pure, unit-tested function, the *same* code is hosted by a
   serverless function in the cloud and a long-running process locally, and both produce
   **identical metrics**. That is what makes the two pipelines interchangeable.

### The full local ↔ cloud mapping

| Role | Cloud (AWS) | Local (Docker Compose) |
|---|---|---|
| Ingest / fan-out to browsers | `traffic-ingest` Lambda (via WebSocket API Gateway + DynamoDB connections) | the emitter's own WebSocket server broadcasts directly (point-to-point on one machine — no separate ingest needed) |
| Per-tick metrics → InfluxDB | `traffic-metrics` Lambda (`compute_tick_metrics`) | `metrics_writer.py` (same `compute_tick_metrics`) |
| History / replay read API | `traffic-replay` Lambda | `replay_server.py` (stdlib HTTP server) |
| Time-series store | InfluxDB Cloud | InfluxDB container |

**Framing for the viva:** this is a *separation of concerns* — application logic
(pure functions) vs. the infrastructure that hosts it. The cloud uses serverless Lambda
because it is cost-efficient and auto-scaling for an intermittent public pipeline; the
local stack uses a long-running process because, on a single already-running machine, that
is the simplest right-sized host. Sharing `compute_tick_metrics` across both guarantees the
local and cloud results match, which is also why the metrics are tested once and trusted
everywhere.

---

## Q5. How were the SUMO input files (`*.net.xml`, `traffic_trips.routed.rou.xml`, `*.add.xml`) built?

**Key point: these three are the *calibrated simulation core* — built once by the Python
pipeline from real OpenStreetMap + Christchurch City Council data, then consumed unchanged.**
They are prior/inherited assets (marked "do not modify" in `CLAUDE.md`); this project adds
the streaming / cloud / decision-support layer on top of them. The main SUMO config wires
all three together:

```
<net-file          value="…/Christchurch_Central_City_main_streets.net.xml" />
<route-files       value="…/traffic_trips.routed.rou.xml" />
<additional-files  value="…/Christchurch_Central_City_main_streets.add.xml" />
```

### 1. `Christchurch_Central_City_main_streets.net.xml` — the road network
Built by **`create_network.py`** (the "network" step in `sim_pipeline.py`):
1. Take an **OpenStreetMap** extract of the central city (`Christchurch_Central_City.osm.xml`).
2. Filter it to the **main streets** (drop footpaths, service lanes, etc.).
3. Run SUMO's **`netconvert`** to turn OSM ways into a routable SUMO network — lanes,
   junctions, connections, speeds — then **rebuild the traffic-light logic (TLS)**.
   (The net is `lefthand="true"` — New Zealand drives on the left.)

The same script's "map" step also produces `intersection_to_edges.csv` by matching the
**CCC OpenData / ArcGIS intersection geometry** (`intersection_geo.csv`, the 96 surveyed
intersections) to the nearest net edges — the mapping the dashboard's road overlay and
`edge_to_intersection.py` use.

### 2. `Christchurch_Central_City_main_streets.add.xml` — map-context polygons
Generated by SUMO's **`polyconvert`** (per the file's own header, v1.26.0) from the **same
OSM file** plus the net: it extracts **area polygons** — buildings, parks/leisure,
amenities, parking — pruned to the network's bounds (`prune.in-net=true`). This is purely
**visual context** for `sumo-gui` (the grey/green shapes behind the roads); it contains **no
detectors or traffic logic** (a common misconception — "additional file" ≠ sensors here).

### 3. `traffic_trips.routed.rou.xml` — the vehicle demand (routes)
Built by **`create_demand.py`** (the "trips" then "duarouter" steps), from the **real CCC
Miovision turning-movement counts**:
1. Count workbooks (Excel) → **`traffic_counts_parser.py`** → one long CSV of surveyed
   movements (intersection, approach, movement, time slot, vehicle count).
2. **`sumo_demand_from_traffic_csv.py`** turns each surveyed movement into a SUMO **`<flow>`**
   — a vehicle `number` on a `from`→`to` edge pair, in a 15-minute slot — producing
   `traffic_trips.rou.xml` (origin/destination demand, not yet routed).
3. SUMO's **`duarouter`** computes a shortest-path **route through the net** for every
   OD pair, producing `traffic_trips.routed.rou.xml` — fully-routed vehicles with explicit
   edge lists, which is what SUMO actually runs. (Buses are built the same way from a
   timetable into `traffic_trips_timetable_buses.routed.rou.xml`.)

### The chain, end to end
```
OpenStreetMap  ──netconvert──▶  net.xml          (roads, junctions, TLS)
OpenStreetMap  ──polyconvert─▶  add.xml          (building/park polygons — gui only)
CCC intersection geometry ─match▶ intersection_to_edges.csv

CCC Miovision counts ─parser▶ CSV ─flows▶ traffic_trips.rou.xml ─duarouter▶ traffic_trips.routed.rou.xml
```

**Framing for the viva:** the network and demand are *calibrated from real data* — OSM for
the road geometry, CCC OpenData for intersection placement, and CCC/Miovision counts for how
many vehicles make each movement. That real-data calibration is exactly what makes the
baseline defensible (and what the GEH validation in §4.2 checks the simulation reproduces).
The build is deterministic and re-runnable (`create_network.py` → `create_demand.py`), but
the committed outputs are treated as fixed inputs so the streaming/cloud work builds on a
stable model.
