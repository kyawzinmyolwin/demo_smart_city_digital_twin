# Project checklist — demo_smart_city_digital_twin

COMP 693 Industry Project. Snapshot of what's done and what's left.
Source of truth for detail is `CLAUDE.md`; this is the quick status view.
_Updated 2026-10-03._

## ✅ Done

### Core build (Phase 1 + cloud pipeline)
- [x] JSON emitter + WebSocket server (`run_traci.py --emit`, `emitter.py`) — unit-tested
- [x] Live dashboard: WebSocket vehicle layer, speed-coloured markers, 3 Chart.js panels, pause/resume
- [x] Cloud pipeline (Terraform): WebSocket API Gateway → ingest/metrics/replay Lambdas → InfluxDB Cloud; S3+CloudFront; Secrets Manager; billing alarm — deployed & verified
- [x] Emitter → cloud forwarding (`--emit-target`); on-demand EC2 sim host
- [x] Local metrics pipeline (`metrics.py`, `metrics_writer.py`) + InfluxDB; history charts

### Decision-support twin (the pivot)
- [x] Incident-injection hook — close edge/lane, speed limit, demand surge (`incidents.py`, `--incident-file`/`--close-edge`)
- [x] Edge tooling — `list_edges.py`, `edges_geojson.py`, clickable road overlay
- [x] ETL → scenario baseline bridge (`scenario_bridge.py`, `fetch_counts_for_date.py`)
- [x] Scenario-tagged metrics (`--scenario-id` → InfluxDB tag, local + cloud)
- [x] Compare view (baseline vs incident) + quantified summary line
- [x] Congestion-alert overlay (slow-segment flagging + red highlight)
- [x] Click-to-inject (local ws) — close a road live from the map, with a **Close live ↔ Reopen road** toggle (block then resume in one run) + a visible sim clock
- [x] GUI scenario control (`control_server.py` + panel) — start/stop from the browser, no CLI; **click a road → Start road block** (immediate close from 06:30)
- [x] Cloud deploy wired (`deploy_dashboard.sh`: live feed, overlay, history, compare on hosted page)
- [x] Impact report (Inc 4 v1) — baseline-vs-incident metrics table (avg speed, congestion, stopped mean/peak, vehicles) with directional Δ
- [x] Auto-start `metrics_writer` from `control_server.py` with each scenario (stop on Stop; `--no-writer` to opt out) — the GUI path now fills InfluxDB with no separate writer terminal
- [x] One-command local demo: `start_demo.sh` / `stop_demo.sh` (InfluxDB + dashboard web + replay + control servers, pidfiles/logs in `.demo/`) — a non-IT user runs `./start_demo.sh` then clicks a Start button

## ⏳ To do

### Committed / planned
- [ ] **Increment 4 v2 (optional)** — true per-vehicle delay (`timeLoss`) + affected-area; needs new emitted fields
- [ ] **Milestone 5 — Docker Compose one-command bring-up** (sim + read server + InfluxDB) — proposal-committed, due 19 Oct
- [ ] **Milestone 5 — GitHub Actions CI/CD** (run the test suite on push) — proposal-committed
- [ ] Final technical report (evaluate against proposal goals)

### Phase 3 — portfolio wrap-up
- [ ] Final README, screenshots, live demo URL
- [ ] 2-min demo recording + architecture diagram
- [ ] CV / LinkedIn write-up

### Deferred by choice (not scheduled)
- [ ] Incident rerouting / detours (~6–9h)
- [ ] Cloud control path for click-to-inject + cloud start/stop (API Gateway + SSM)
- [ ] Historical replay scrub bar — de-prioritised (counts replay is now the baseline)

## 📌 Loose ends worth closing
- [ ] Confirm the scope pivot (decision-support twin) with the supervisor at a milestone review
- [ ] On the hosted page, re-run `terraform apply` + fresh `scenario_id` runs so the cloud compare view has tagged data
- [ ] Rebuild intersection-graph net if you want the counts→CBD scenarios (needs `christchurch_intersections.net.xml`)

---

**Headline:** the decision-support feature set is essentially complete and deployed.
The main remaining weight is **Milestone 5 (Docker + CI/CD, due 19 Oct)** — a committed
milestone still at zero — plus the final report. Increment 4 is a small, optional polish.
