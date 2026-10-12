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
