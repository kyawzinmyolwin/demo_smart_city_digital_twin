# Final Technical Report — Christchurch Smart-City Digital Twin

**COMP 693 Industry Project · Lincoln University, NZ**
Repository: `kyawzinmyolwin/demo_smart_city_digital_twin`

---

## 1. Executive summary

The project delivers a **decision-support traffic digital twin** of the
Christchurch central city. A calibrated SUMO micro-simulation — built from real
Christchurch City Council, OpenStreetMap, and Miovision data — streams live vehicle
state to a browser dashboard and to a cloud time-series pipeline. On top of that
real-time backbone, the twin can be **perturbed** (close a road, stage a crash, add
an event surge) and the impact **measured** against a real-data-calibrated baseline.

All core objectives from the proposal were met, and the headline extension feature
set was redirected mid-project (with rationale, §3) from passive historical replay to
active **what-if decision support** — the defining purpose of a digital twin. Both
committed Milestone-5 engineering deliverables (Docker Compose one-command demo and
GitHub Actions CI/CD) are complete, alongside documentation and this report.

**At a glance**

| Area | Outcome |
|---|---|
| Real-time emitter + WebSocket | Done, unit-tested, verified live |
| Cloud pipeline (AWS, Terraform) | Built, deployed, verified end-to-end |
| Live dashboard | Done + extended with decision-support panels |
| Decision-support features | Incident injection, scenario compare, impact report, congestion alerts, live click-to-inject |
| One-command demos | `docker compose up` and `start_demo.sh` |
| CI/CD | GitHub Actions, 86 tests green on Python 3.11 + 3.12 |
| Code | ~33 Python modules, 12 Terraform files, a 1,600-line dashboard, 86 unit tests |

---

## 2. Objectives (from the proposal)

The proposal set a 300-hour build across three phases plus an extension budget:

- **Phase 1 — real-time data:** extend the existing SUMO simulation to emit vehicle
  state as JSON over WebSocket every step.
- **Phase 2 — cloud pipeline:** a public WebSocket endpoint (AWS API Gateway), Lambda
  metrics aggregation, InfluxDB Cloud storage, infrastructure-as-code (Terraform), and
  a GitHub Actions CI/CD pipeline.
- **Phase 3 — live dashboard:** extend the existing Leaflet map with a WebSocket
  client, speed-coloured vehicle markers, three Chart.js panels (count / average speed
  / density), a pause/resume control, and static hosting (S3 + CloudFront / Pages).
- **Extension features (~100 h):** (1) congestion alerts, (2) scenario comparison,
  (3) historical replay, (4) threshold metrics panel, (5) Docker Compose one-command
  bring-up.

The simulation core (SUMO network, demand, `sim_pipeline.py`, the Unity 3D twin) was
**pre-existing and out of scope** — everything cloud-, data-, and dashboard-related
was built in this project.

---

## 3. Scope change: the decision-support pivot

**Decision (2026-09-16):** the Phase-2 extension work pivoted from a *historical
replay* twin to a *scenario / decision-support* twin.

**Rationale.** Replaying historical counts on the simplified intersection graph is
*estimation* over sparse, peak-only survey data with known connectivity gaps — hard to
defend as "real". Injecting incidents into the **strong, calibrated street-network
model** and measuring the result is (a) the actual point of a digital twin, (b)
honestly framed as synthetic, and (c) technically smaller, lower-risk work.

**What was kept, not dropped.** The counts → demand ETL pipeline remains as the
real-data-calibrated **baseline** that incidents are compared against, and as a
legitimate cloud-engineering showcase (S3 + Lambda ETL, tested).

**Mapping to the proposal.** The pivot *supersedes* two extension line items with
stronger equivalents and keeps the rest:

| Proposal extension item | Delivered as |
|---|---|
| (2) Scenario comparison | **Increment 2** — `scenario_id`-tagged metrics + dashboard compare view + impact report |
| (1) Congestion alerts | **Increment 3** — live congestion-alert overlay |
| (4) Threshold metrics panel | Folded into the congestion overlay |
| (3) Historical replay | De-prioritised (counts replay is now the baseline, not a headline); scrub bar deferred |
| (5) Docker Compose | **Delivered** (Milestone 5) |

The change was logged in `CLAUDE.md` and is recommended for confirmation with the
supervisor at a milestone review.

---

## 4. System architecture

One **producer** (SUMO + the TraCI emitter) feeds one of two interchangeable
**pipelines** — a local InfluxDB stack or the AWS cloud stack — and a single HTML
**dashboard** points at whichever endpoints it is given. Full diagrams (data flow,
local deployment, cloud deployment) and a component/port reference are in
[ARCHITECTURE.md](ARCHITECTURE.md). In brief:

```
SUMO ⇄ run_traci.py --emit ──(WebSocket JSON/tick)──▶ dashboard (live map + charts)
                              │
                              ├─▶ metrics_writer ─▶ InfluxDB ◀─ replay_server ─▶ dashboard (history/compare)
                              └─▶ (--emit-target) ─▶ API Gateway ─▶ ingest λ ─▶ metrics λ ─▶ InfluxDB Cloud
                                                                       replay λ ─▶ dashboard;  CloudFront+S3 serves it
```

The per-tick metric computation (`compute_tick_metrics`) is a **pure function reused
verbatim** on both pipelines — a local module and the body of the `traffic-metrics`
Lambda — so local and cloud produce identical metrics.

---

## 5. Implementation

### 5.1 Real-time emitter (Phase 1)
`run_traci.py --emit` wraps the existing synchronous TraCI loop in an `asyncio` event
loop and broadcasts a JSON snapshot per tick over WebSocket (`:8765`); SUMO XY is
converted to WGS84 via `sumolib`. New clients get an immediate snapshot; tick rate is
throttleable (`--emit-interval`). The serialiser (`emitter.py::serialize_vehicles`) is
unit-tested against a fake `traci` with no SUMO dependency. The original non-emit
behaviour is untouched.

### 5.2 Incident injection (Increment 1)
`incidents.py` models closures and perturbations (`close_edge`, `close_lane`,
`set_speed`, `add_vehicles`) with apply-and-revert semantics, driven by
`--close-edge`/`--incident-file`/`--scenario-id`. Supporting tooling: edge-picking
helpers (`list_edges.py`, `edges_geojson.py`) and a clickable road overlay on the map.

### 5.3 Metrics pipeline (Phase 2, local + cloud)
`metrics.py::compute_tick_metrics` (pure, unit-tested) computes vehicle count, average
speed, congestion index, and stopped/moving counts. `metrics_writer.py` consumes the
WebSocket feed and writes to InfluxDB, tagged by `simId` **and** `scenario_id`.
`replay_server.py` is the local read endpoint (Flux range queries, CORS, a validated
`scenario` filter) — the dev mirror of the `traffic-replay` Lambda.

### 5.4 Dashboard (Phase 3 + decision-support)
`intersection_map.html` (~1,600 lines) extends the existing Leaflet map with: a
WebSocket live layer (speed-coloured markers), three Chart.js panels, pause/resume, a
live sim clock, a **compare view** (two `scenario_id` runs overlaid + quantified
summary), an **impact report** (speed drop, congestion rise, stopped mean/peak with
directional Δ), a **congestion-alert overlay**, and **click-to-inject** (close a road
live, then a Close ↔ Reopen toggle to watch recovery).

### 5.5 Scenario control & non-IT usability
`control_server.py` (`:8799`) starts/stops **named presets only** (never arbitrary
args) from the browser, and auto-starts the metrics writer so the GUI path fills
InfluxDB without a second terminal. Two one-command launchers wrap the whole local
stack: `start_demo.sh`/`stop_demo.sh` (host processes) and `docker compose up`
(containers — see §6).

### 5.6 Cloud infrastructure (Phase 2)
`infra/` (12 Terraform files) provisions a WebSocket API Gateway, three Lambdas
(ingest / metrics / replay), a DynamoDB connections table, S3 + CloudFront dashboard
hosting, Secrets Manager (InfluxDB token), and CloudWatch logs with a \$5 billing
alarm, in `ap-southeast-2`. Verified end-to-end (live SUMO → API Gateway → Lambdas →
InfluxDB Cloud). An optional, cost-gated EC2 sim host can run the producer in AWS.

### 5.7 ETL baseline
`scripts/etl/` + `scenario_bridge.py` turn Council counts into calibrated
demand/baseline data, with S3 storage and ingest/query Lambdas — retained as the
real-data comparison path (45 unit tests, AWS mocked with `moto`).

---

## 6. Milestone 5 engineering deliverables

- **Docker Compose one-command demo.** `docker compose up` builds a SUMO image
  (`ppa:sumo/stable`, the recipe proven in `sim_host.tf`) and a slim Python image, then
  runs InfluxDB + sim + writer + replay + dashboard, with code/data bind-mounted.
  Guide: [DOCKER.md](../DOCKER.md).
- **GitHub Actions CI/CD.** `.github/workflows/ci.yml` runs the full unit suite on
  every push and pull request across a Python 3.11 + 3.12 matrix (test deps pinned in
  `requirements-dev.txt`, pip-cached). A second workflow publishes the dashboard to
  GitHub Pages.

---

## 7. Evaluation against proposal goals

| Objective | Status | Evidence |
|---|---|---|
| P1 — JSON/WebSocket emitter, every step, configurable rate | ✅ Met | `run_traci.py --emit`, `emitter.py`; 6 tests |
| P2 — API Gateway WebSocket endpoint | ✅ Met | `infra/api_gateway.tf`; verified |
| P2 — Lambda metrics aggregation | ✅ Met | `traffic-metrics` λ = `compute_tick_metrics`; 6 tests |
| P2 — InfluxDB Cloud storage | ✅ Met | writes verified (local + cloud) |
| P2 — Infrastructure as code (Terraform) | ✅ Met | 12 `.tf` files, applied |
| P2 — GitHub Actions CI/CD | ✅ Met | `ci.yml`, 86 tests, 3.11+3.12 |
| P3 — WebSocket client + speed-coloured markers | ✅ Met | `intersection_map.html` |
| P3 — Three Chart.js panels | ✅ Met | count / avg speed / congestion |
| P3 — Pause/resume | ✅ Met | live control |
| P3 — Static hosting (S3/CloudFront + Pages) | ✅ Met | `cdn.tf`, `deploy-dashboard.yml` |
| Ext 1 — Congestion alerts | ✅ Met | congestion overlay (Inc 3) |
| Ext 2 — Scenario comparison | ✅ Exceeded | compare view + **impact report** (Inc 2/4) |
| Ext 3 — Historical replay (scrub bar) | ⚠️ Deferred | superseded by the pivot; counts replay is the baseline |
| Ext 4 — Threshold metrics panel | ✅ Folded | into the congestion overlay |
| Ext 5 — Docker Compose | ✅ Met | `docker-compose.yml`, `docker/` |
| Beyond proposal | ➕ Added | incident injection, live click-to-inject + recovery, GUI scenario control, impact report, ETL baseline bridge, one-command launchers |

**Summary:** every core objective met; the extension set delivered as a stronger
decision-support feature set, with one proposal item (historical replay scrub bar)
deliberately deferred by the pivot and several capabilities added beyond the proposal.

---

## 8. Testing & quality

- **86 unit tests**, all green on Python 3.11 and 3.12:
  - 41 core (`scripts/tests/`): incidents (14), control_server (11), emitter (6),
    metrics (6), replay_server (4).
  - 45 ETL (`scripts/etl/tests/`): scenario bridge (9), counts ETL (7), ingest (7),
    query (6), drive client (6), lambda query (4), lambda ingest (3), s3 store (3).
- **Pure-core / thin-glue** design: business logic is tested against fakes (`traci`,
  `Popen`) and mocks (`moto` for AWS) — no SUMO, cloud, or network needed in CI.
- Dashboard JavaScript is syntax-checked with `node --check`.
- CI enforces the suite on every push and pull request.

---

## 9. Engineering practices

Infrastructure-as-code (Terraform) with least-privilege IAM and no hard-coded secrets
(Secrets Manager); one logical change per commit with a consistent attribution footer;
feature-branch workflow; cost controls (billing alarm, cost-gated sim host); layered
documentation (`README`, `ARCHITECTURE`, `DOCKER`, `METRICS_REPLAY`, `running_guide`,
`infra/README`, `CHECKLIST`, `CLAUDE.md`).

---

## 10. Known limitations & honest caveats

- **Incidents are synthetic.** The twin perturbs a calibrated model; it does not
  ingest live road-sensor data (the Council sources are download-only).
- **A "closed" edge is a hard speed cap, not rerouting.** Traffic queues/crawls rather
  than diverting; incident rerouting is scoped and deferred (§11).
- **Cloud click-to-inject is local-only.** Live injection works over the local
  WebSocket; driving it from the hosted dashboard needs a cloud control path (deferred).
- **Replay public URL.** A Lambda Function URL 403s anonymously on this account; the
  dashboard uses an API-Gateway-fronted replay instead.
- **Docker `sim` image** is validated with `docker compose config` and uses the proven
  SUMO recipe, but a full container build/run should be exercised on the target VM.
- **Compare uses per-series aggregates**, not timestamp alignment (the two runs occur
  at different wall-clock times) — appropriate for the metrics compared.

---

## 11. Future work

- Incident **rerouting / detours** (TraCI `adaptTraveltime` + `rerouteTraveltime`,
  `--time-to-teleport -1`), ~6–9 h.
- **Cloud control path** for click-to-inject (API Gateway control route + SSM).
- Impact report **v2**: true per-vehicle delay (`traci.vehicle.getTimeLoss`) and
  affected-area; recovery-time after reopen.
- Portfolio wrap-up: dashboard screenshots + live-demo URL in the README, and a
  2-minute demo recording.

---

## 12. Conclusion

The project delivers a working, cloud-connected, tested, and reproducibly deployable
decision-support digital twin of Christchurch's central-city traffic. It meets the
proposal's core objectives and re-aims the extension work at genuine what-if decision
support — the substance of a digital twin — while retaining the real-data pipeline as a
calibrated baseline. The engineering deliverables (one-command demos, CI across two
Python versions, infrastructure-as-code, and layered documentation) make it both
demonstrable and defensible as an industry-project portfolio piece.

---

*Status detail: [CHECKLIST.md](../CHECKLIST.md) · Architecture: [ARCHITECTURE.md](ARCHITECTURE.md) · Decisions & history: [CLAUDE.md](../CLAUDE.md)*
