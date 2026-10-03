# Project recap — catch-up guide

A narrative overview to get back up to speed quickly. For the tick-box status see
`CHECKLIST.md`; for how to run things see `COMMANDS.md`; for full detail see `CLAUDE.md`.
_Updated 2026-10-03._

---

## 1. What this project is now (in one paragraph)

A Christchurch CBD traffic **digital twin**: a calibrated SUMO simulation whose live
state streams to a browser dashboard, backed by a cloud pipeline. It started as "stream
the sim to the cloud and show it on a map," and has since become a **scenario /
decision-support twin** — you inject a *what-if* (a crash/road closure, a roadworks speed
limit, an event surge), watch the impact live, and compare it against a normal baseline
with real numbers.

---

## 2. The journey, in order

**Stage A — Core build (before this stretch of work).**
The emitter (`run_traci.py --emit` + `emitter.py`), the live Leaflet dashboard, and the
full AWS pipeline (API Gateway → Lambdas → InfluxDB Cloud, in Terraform) were built and
deployed. This is the streaming/cloud spine.

**Stage B — Counts → CBD scenarios (early in this stretch).**
We tried to build simulation scenarios from real CCC Miovision traffic counts (the ETL
pulls workbooks from the council's public Drive). We got it working but learned two hard
truths: the surveys are **peak-only** (≈07:00–09:00 and ≈13:00–18:00, 45 sparse days), and
turning-counts→routes is an *estimation* on a schematic graph. Useful as a real-data
**baseline**, weak as a headline.

**Stage C — The pivot (2026-09-16).**
Because of B, we changed direction: instead of replaying historical data, the twin now
**perturbs the strong, calibrated model** and measures the effect. This is the actual point
of a digital twin, is honestly framed as synthetic, and is less work than perfecting the
counts path. The counts/ETL work stays as the baseline + a cloud-engineering showcase.

**Stage D — Decision-support features (the bulk of recent work).**
Built in increments:
- **Incident injection** — close an edge/lane, set a speed limit, or add a demand surge,
  via TraCI, timed, reversible.
- **Edge tooling** — find roads by name / on the map (`list_edges.py`, `edges_geojson.py`,
  a clickable road overlay) so you don't hand-type edge IDs.
- **Scenario comparison** — tag each run with a `scenario_id`, store its metrics, and
  overlay baseline vs incident on the dashboard with a quantified summary ("−38%, worse").
- **Congestion alerts** — flag and red-highlight segments slow for N consecutive ticks.
- **Click-to-inject** — click a road on the map to close it in the *running* sim.
- **GUI scenario control** — Start/Stop preset scenarios from the browser (no command
  line), so a non-IT user can drive the whole thing.

**Stage E — Deploy + docs.**
The hosted CloudFront dashboard now serves the live feed, road overlay, history and compare
view (the old replay-URL 403 is gone). Along the way we kept the weekly journals (Weeks 9,
10), a command reference (`COMMANDS.md`), a design note, and a status checklist.

---

## 3. The mental model — how the pieces fit

```
                 SUMO  ──TraCI──►  run_traci.py   (steps the sim; applies incidents)
                                        │ emits a JSON snapshot per tick
                                        ├───────────────► local WebSocket :8765 ──► dashboard (live vehicles)
                                        │                       ▲ (click-to-inject commands go back up this socket)
                                        └── --emit-target ─► AWS API Gateway (wss)
                                                                   ├─► ingest Lambda ─► broadcasts to browsers
                                                                   └─► metrics Lambda ─► InfluxDB Cloud
   control_server.py  ──spawns──►  run_traci.py (preset scenarios: baseline / crash / roadworks)

   dashboard (intersection_map.html) reads, via URL params:
     ?ws=       live vehicle feed (local :8765 or the cloud wss)
     ?replay=   history + compare charts  (replay_server.py local, or the replay Lambda)
     ?counts=   CCC counts (the ETL query API)
     ?edges=    road overlay geometry (edges_geojson.py output)
     ?control=  start/stop scenarios (control_server.py)
```

Key idea: **everything flows from one per-tick JSON snapshot.** The dashboard, the metrics
store, and the compare view are all just different consumers of that stream; incidents and
`scenario_id` are things we add *into* the run that then ride along in the snapshot.

---

## 4. Decisions worth remembering (the "why")

- **Pivot to decision-support** — builds on the calibrated model, honestly synthetic,
  smaller + more defensible than the counts replay. (Confirm with the supervisor.)
- **Incidents are synthetic what-ifs**, not observed events — a stated strength for the report.
- **Local vs cloud** — click-to-inject and the GUI control server are **local/VM** features
  (they talk to a running sim / spawn processes); the hosted CloudFront page can't reach a
  localhost server. Cloud versions are deliberately deferred.
- **Closures model a block by stopping entry** (vehicles queue upstream); rerouting *around*
  a closure is a separate, deferred feature.
- **Pure-core + thin-glue + unit tests** — the logic (metrics, incidents, bridge, control)
  is tested without SUMO/AWS; the thin glue talks to the real systems. ~74 tests.

---

## 5. New components (quick reference)

| File | What it does |
|---|---|
| `incidents.py` | Incident spec + controller (close/speed/surge via TraCI) |
| `scenario_bridge.py`, `fetch_counts_for_date.py` | ETL counts → scenario CSV (baseline) |
| `list_edges.py`, `edges_geojson.py` | Find / map road edges for incidents |
| `make_cbd_scenario.py` | Build a counts-driven CBD scenario |
| `metrics.py`, `metrics_writer.py` | Per-tick metrics → InfluxDB (scenario-tagged) |
| `replay_server.py` | Local read API for history/compare charts |
| `control_server.py` | Start/stop preset scenarios from the browser |
| `intersection_map.html` | The dashboard — live map + all the panels above |
| `scenarios/DECISION_SUPPORT_DESIGN.md` | The scenario/success-criteria design note |

---

## 6. Where we are / what's next

**Done:** the whole decision-support feature set, deployed and working.

**Next (by priority):**
1. **Milestone 5** — Docker Compose one-command bring-up + GitHub Actions CI/CD. *Committed,
   due 19 Oct, not started — the real remaining weight.*
2. **Increment 4** — impact metrics/reporting (added delay, peak queue, affected area):
   small polish on the compare summary.
3. **Final report** + Phase 3 portfolio wrap-up (README, demo video, screenshots).

**Deferred by choice:** incident rerouting/detours, cloud control path, historical replay
scrub bar.

---

## 7. If you only remember five things

1. The twin now answers **"what if this road closes?"**, not just "show me traffic."
2. It all rides on **one per-tick JSON snapshot** from `run_traci.py`.
3. **Scenario comparison** (baseline vs incident, with a % impact) is the headline feature.
4. **Click-to-inject + GUI control** are **local-only**; the cloud page is view-only for those.
5. The big remaining task is **Milestone 5 (Docker + CI/CD)**, then the report.
