# Metrics, Replay server & InfluxDB — operations guide

How the time-series side of the twin fits together, how to run it, and how to fix the
things that actually went wrong. Scope: `metrics_writer.py`, `replay_server.py`, the local
InfluxDB container, and the dashboard panels that read them (History / Compare / Impact).
For the full command list see `COMMANDS.md`; for the big picture see `RECAP.md`.
_Updated 2026-10-05._

---

## 1. The components and how they relate

| Component | Role | Port |
|---|---|---|
| **SUMO + `run_traci.py --emit`** | Runs the sim; broadcasts one JSON snapshot per tick over a WebSocket (the *emitter*). | 8765 |
| **`metrics_writer.py`** | Subscribes to the emitter WS, runs `compute_tick_metrics()` on each snapshot, **writes** the result to InfluxDB. | — |
| **InfluxDB** (`cdt-influxdb`, `influxdb:2.7`) | Time-series store. Org `christchurch`, bucket `traffic-metrics`, measurement `traffic_metrics`. | 8086 |
| **`replay_server.py`** | HTTP **read** endpoint: proxies Flux range queries to InfluxDB and returns JSON (holds the token, adds CORS). | 8788 |
| **Dashboard** `intersection_map.html` | History / Compare / Impact panels **fetch** from `replay_server`; the live map reads the emitter directly. | 8000 (served) |

**The golden rule:** the live map comes **straight from the emitter**; everything historical
(History, Compare, Impact) comes **from InfluxDB via `replay_server`**. So the live map can
work perfectly while History is empty — they are different paths.

**Write path:** `SUMO → emitter (8765) → metrics_writer → InfluxDB (8086)`
**Read path:** `dashboard → replay_server (8788) → InfluxDB (8086)`

What's stored per tick: measurement `traffic_metrics`, tags `simId` + `scenario_id`,
fields `vehicleCount`, `avgSpeed` (m/s), `congestionIndex`, `stoppedCount`, `movingCount`,
`simTime`. Timestamp = write time (now), not sim time.

---

## 2. Architecture diagram

```
                         ┌─────────────────────────────────────────────┐
   SUMO ──TraCI(8813)──► │ run_traci.py --emit --emit-host 0.0.0.0     │
                         │   • steps the sim                            │
                         │   • one JSON snapshot / tick                 │
                         └───────────────┬──────────────────────────────┘
                                         │  ws://…:8765   (the emitter)
                        ┌────────────────┼───────────────────────────┐
                        │ (live map)     │ (metrics)                  │
                        ▼                ▼                            
         ┌──────────────────────┐   ┌──────────────────────────┐
         │ dashboard live layer │   │ metrics_writer.py        │
         │ (?ws=…:8765)         │   │   compute_tick_metrics() │
         └──────────────────────┘   │   write → InfluxDB       │
                                     └───────────┬──────────────┘
                                                 │ http  :8086  (WRITE)
                                                 ▼
                                   ┌──────────────────────────────┐
                                   │ InfluxDB  (cdt-influxdb)      │
                                   │ org=christchurch             │
                                   │ bucket=traffic-metrics       │
                                   │ measurement=traffic_metrics  │
                                   └───────────┬──────────────────┘
                                                 ▲ http  :8086  (READ, holds token)
                                                 │
                                   ┌─────────────┴────────────────┐
                                   │ replay_server.py  :8788       │
                                   │  GET /metrics?field=&start=   │
                                   │       &stop=&every=&scenario= │
                                   └─────────────┬─────────────────┘
                                                 ▲ http  :8788  (fetch + CORS)
                                                 │
                         ┌───────────────────────┴───────────────────────┐
                         │ dashboard panels: History · Compare · Impact   │
                         │ (?replay=http://localhost:8788/metrics)        │
                         └────────────────────────────────────────────────┘

   Cloud variant (separate): run_traci --emit-target wss://…/prod → API Gateway →
     ingest/metrics Lambdas → InfluxDB CLOUD; the hosted dashboard's ?replay= points at
     the traffic-replay Lambda (API Gateway). LOCAL and CLOUD InfluxDB are different stores.
```

---

## 3. CLI commands — one per terminal (local demo, on the VM)

Run each in its **own terminal**, from the venv with `SUMO_HOME` set. Don't chain with
`&&` — these are long-running servers.

```bash
# ── prerequisites (once) ───────────────────────────────────────────────────
cd ~/demo_smart_city_digital_twin/smart_city_digital_twin/2D_simulation
source .venv/bin/activate          # emitter/writer/replay need pyproj + websockets + influxdb-client
echo "$SUMO_HOME"                    # must be set for run_traci

# ── Terminal 0: InfluxDB container (repo root) ─────────────────────────────
cd ~/demo_smart_city_digital_twin
#   with compose v2:  docker compose up -d
#   with compose v1:  docker-compose up -d
#   no compose:       docker run (see §5, "Connection refused")
curl -s http://localhost:8086/health            # {"status":"pass"} before continuing

# ── Terminal 1: dashboard web server (served from 2D_simulation) ───────────
cd ~/demo_smart_city_digital_twin/smart_city_digital_twin/2D_simulation
python3 -m http.server 8000 --bind 0.0.0.0

# ── Terminal 2: the simulation + emitter ───────────────────────────────────
python3 scripts/run_traci.py --no-gui --emit --emit-host 0.0.0.0 --real-time --speed 5 \
  --jump-to 23400 --scenario-id baseline_am

# ── Terminal 3: metrics writer (WRITES to InfluxDB) ────────────────────────
python3 scripts/metrics_writer.py --ws-url ws://localhost:8765

# ── Terminal 4: replay server (dashboard READS from here) ──────────────────
python3 scripts/replay_server.py --influx-url http://localhost:8086
```

Open the dashboard on the Mac: `http://localhost:8000/scripts/intersection_map.html`
→ History panel → field + range → **Load**.

**Port forwarding (Mac → VM):** forward **8000, 8765, 8788, 8799** (and 8086 only if you want
the InfluxDB UI on the Mac). Vagrantfile:
```ruby
config.vm.network "forwarded_port", guest: 8000, host: 8000
config.vm.network "forwarded_port", guest: 8765, host: 8765
config.vm.network "forwarded_port", guest: 8788, host: 8788
config.vm.network "forwarded_port", guest: 8799, host: 8799
```

> Scenario-control GUI note: `control_server.py` (8799) starts the sim+emitter for you, but
> **not** `metrics_writer.py` — so Terminal 3 must still be run by hand for History/Compare to
> have data. (Auto-starting it is a logged enhancement.)

---

## 4. Troubleshooting — symptom → check → fix

| Symptom | Check | Fix |
|---|---|---|
| History/Compare empty, **no error** | Is `metrics_writer.py` running? Is there data in InfluxDB? | Run the writer (Terminal 3) alongside a live sim. The GUI start does **not** launch it. |
| Writer: **"Could not connect to emitter"** | Is a sim running on 8765? | Start Terminal 2 first (or start the writer within its `--connect-timeout`, default 60 s). |
| Writer: **`[Errno 111] Connection refused`** | `curl http://localhost:8086/health` on the writer's host | InfluxDB container isn't up on that host — start it (§5), or point `--influx-url` at where it is. |
| `docker compose` → **unknown command** / `docker-compose` **not found** | — | Install compose, or use the `docker run` fallback (§5). |
| Docker: **`PermissionError(13) Permission denied`** | socket permission | `sudo usermod -aG docker $USER` then re-login (or prefix `sudo`). |
| Replay direct URL returns **empty points** | Does the writer and replay use the **same** InfluxDB/org/bucket? Direct Flux query (§5) | Point both at the same instance; confirm `replay_server` startup line shows the right url/bucket. |
| Dashboard: **"fetch failed — is the replay server running?"** | From the Mac browser open `http://localhost:8788/metrics?field=avgSpeed&start=-1h` | If it can't connect: forward **8788**, and ensure `replay_server` binds `0.0.0.0` (§5). |
| Hosted (CloudFront) History empty but local works | Which InfluxDB? | The hosted page's `?replay=` reads **InfluxDB Cloud**; local `metrics_writer` writes **local**. Different stores (§5). |

Decisive direct test (run from the **Mac** browser — not the VM):
```
http://localhost:8788/metrics?field=avgSpeed&start=-1h
```
`can't connect` → port/bind problem · `{"points":[]}` → wrong/empty store · points → read path OK.

---

## 5. Root causes & fixes (what actually went wrong, 2026-10)

1. **InfluxDB empty because the writer was never running.** The GUI "Start" launches the
   emitter, not `metrics_writer.py`; the live map worked but History/Compare stayed empty.
   *Fix:* run `metrics_writer.py` in its own terminal alongside the sim. *(Enhancement logged:
   have `control_server.py` auto-start it.)*

2. **No local Docker Compose.** `docker compose` → "unknown command"; `docker-compose` → not
   installed. *Fix:* install the v2 plugin (`apt-get install docker-compose-plugin`) or the v1
   package (`apt install docker-compose`), **or** skip compose entirely and run the container:
   ```bash
   cd ~/demo_smart_city_digital_twin
   docker rm -f cdt-influxdb 2>/dev/null
   set -a; . ./.env; set +a
   docker run -d --name cdt-influxdb -p 8086:8086 \
     -e DOCKER_INFLUXDB_INIT_MODE=setup \
     -e DOCKER_INFLUXDB_INIT_USERNAME="${INFLUXDB_USERNAME:-admin}" \
     -e DOCKER_INFLUXDB_INIT_PASSWORD="$INFLUXDB_PASSWORD" \
     -e DOCKER_INFLUXDB_INIT_ORG="${INFLUXDB_ORG:-christchurch}" \
     -e DOCKER_INFLUXDB_INIT_BUCKET="${INFLUXDB_BUCKET:-traffic-metrics}" \
     -e DOCKER_INFLUXDB_INIT_ADMIN_TOKEN="$INFLUXDB_TOKEN" \
     -e DOCKER_INFLUXDB_INIT_RETENTION="${INFLUXDB_RETENTION:-30d}" \
     -v cdt-influx-data:/var/lib/influxdb2 influxdb:2.7
   ```

3. **Docker socket permission denied** (`PermissionError(13)`). The user wasn't in the
   `docker` group. *Fix:* `sudo usermod -aG docker $USER` then re-login (or use `sudo`).

4. **`replay_server` bound to `localhost` → "fetch failed" from the Mac browser.** This was the
   main bug. VirtualBox/Vagrant NAT port-forwarding cannot reach a server bound to `127.0.0.1`
   inside the guest — it targets the VM's NAT interface. The map (8000, `--bind 0.0.0.0`), live
   feed (8765, `--emit-host 0.0.0.0`) and control (8799, `0.0.0.0`) all worked; replay was the
   lone server pinned to `localhost`. *Fix (committed):* `replay_server.py` now binds `0.0.0.0`
   by default (`--host` to override). **Any server you need to reach through VM forwarding must
   bind `0.0.0.0`.**

5. **Local vs Cloud InfluxDB confusion.** `run_traci --emit-target wss://…` sends to the cloud
   pipeline → **InfluxDB Cloud**; `metrics_writer.py` writes to the **local** container. The
   local `replay_server` reads local; the hosted dashboard's `?replay=` reads Cloud. Empty
   History is often "data went to the other store." *Fix:* keep one path consistent — for the
   local demo, write with `metrics_writer.py` and read with the local `replay_server`.

Verify the store directly (mirrors what replay queries):
```bash
cd ~/demo_smart_city_digital_twin && set -a; . ./.env; set +a
curl -s "http://localhost:8086/api/v2/query?org=${INFLUXDB_ORG:-christchurch}" \
  -H "Authorization: Token $INFLUXDB_TOKEN" -H "Accept: application/csv" \
  -H "Content-Type: application/vnd.flux" \
  -d 'from(bucket:"traffic-metrics") |> range(start:-24h) |> limit(n:5)'
```

---

## 6. Quick sanity sequence

1. `curl -s localhost:8086/health` → `pass` (InfluxDB up).
2. Sim running (Terminal 2) → live map shows vehicles + the sim clock ticks.
3. `metrics_writer.py` prints it's writing points (Terminal 3).
4. Mac browser → `http://localhost:8788/metrics?field=avgSpeed&start=-1h` → returns points.
5. Dashboard History → Load → line appears. Compare/Impact then work from the same data.
