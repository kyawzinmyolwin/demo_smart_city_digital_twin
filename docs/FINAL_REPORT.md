**COMP 693 Industry Project — Final Report**

**Project title:** Christchurch Smart-City Decision-Support Digital Twin

**Project type:** Independent Project

**Submitted by:** [Name: to complete]
**Student ID:** [to complete]
**Host Company:** [to complete — independent project; state "N/A (independent project)" if none]
**Name of Mentor / Supervisor:** [to complete]
**Mentor Email:** [to complete]
**Company Address:** [to complete — or "N/A"]
**Date:** [submission date]

**Lincoln University**

---

## Executive Summary

*(Target ~150 words.)*

**Problem Addressed:** Transport planners need to anticipate how incidents — crashes,
road closures, event surges — affect central-city traffic, but Christchurch's open
data is historical and download-only, with no live, interactive way to test "what-if"
scenarios on a realistic model.

**Goal:** Build a decision-support digital twin of the Christchurch CBD that streams a
calibrated SUMO simulation in real time, lets a user inject incidents from the browser,
and measures their impact against a real-data baseline, backed by a cloud data pipeline.

**Methods:** Extended an existing SUMO model with a WebSocket emitter; built an AWS
serverless pipeline (API Gateway, Lambda, InfluxDB Cloud) as Terraform infrastructure-
as-code; extended a Leaflet/Chart.js dashboard with incident injection, scenario
comparison and impact reporting; packaged it with Docker Compose and GitHub Actions CI.

**Outcome:** A working, tested (91 unit tests, CI on two Python versions), reproducibly
deployable twin. Strengths: real-time operation and an honest baseline-vs-incident
comparison runnable with one command. Limitations: incidents are synthetic, and a
closure caps speed rather than rerouting traffic.

---

## Authorship Statement

This report and the accompanying software were prepared with the assistance of
generative-AI tools, disclosed here in the interest of academic integrity.

- **Tool:** Claude Code (Anthropic) — an AI coding assistant.
- **Why it was used:** to accelerate implementation, testing, infrastructure-as-code,
  documentation, and the drafting of this report.
- **How it was used:** under my direction, to draft and refactor code, generate unit
  tests, scaffold Terraform, produce diagrams and documentation, and draft report prose
  from project artefacts. I defined the goals and design decisions, reviewed and
  validated all generated code and text, ran and verified the tests and the system, and
  am responsible for the final content.

*(Please adjust the wording above so it accurately reflects your own working process
and level of involvement before submitting. See also §5.2.)*

---

## Glossary / Acronyms

| Term / acronym | Meaning |
|---|---|
| **Digital twin** | A live, data-driven virtual model of a real system used to monitor and test "what-if" scenarios. |
| **SUMO** | Simulation of Urban MObility — an open-source microscopic traffic simulator. |
| **TraCI** | Traffic Control Interface — SUMO's API for controlling a running simulation step-by-step. |
| **CBD** | Central Business District (here, central Christchurch). |
| **WebSocket** | A protocol for persistent, two-way, real-time messaging over a single connection. |
| **IaC** | Infrastructure as Code — provisioning cloud resources from version-controlled definitions. |
| **Lambda** | AWS serverless function service (runs code without managing servers). |
| **API Gateway** | AWS managed service exposing HTTP/WebSocket endpoints. |
| **InfluxDB** | A time-series database, used here for per-tick metrics. |
| **CI/CD** | Continuous Integration / Continuous Delivery. |
| **CCC** | Christchurch City Council. |
| **OSM** | OpenStreetMap. |
| **Scenario** | A named simulation run (e.g. baseline vs an incident), tagged `scenario_id`. |
| **Congestion index** | A derived metric summarising how slow/stopped traffic is on a tick. |

---

# 1. INTRODUCTION

## 1.1. Overview

This is an **independent software project** undertaken for COMP 693. It does not have an
external host company; the context is a self-directed portfolio project framed around a
realistic problem for a transport authority such as the Christchurch City Council, which
publishes intersection traffic-count and road-geometry open data. The project builds on
an existing SUMO simulation of the Christchurch central city and extends it into a
cloud-connected, interactive decision-support tool.

*(If your proposal framed a specific hypothetical company/service or named a mentor/host,
replace this paragraph with that framing.)*

## 1.2. Problem

A static simulation answers "what does normal traffic look like?" but not the question a
planner actually asks: **"what happens if this road closes, or a crash blocks that
arterial, or an event floods the centre?"** Christchurch's open traffic data is
historical and download-only — there is no live sensor feed and no interactive way to
test interventions. Running these experiments by hand (editing simulation configs,
re-running, manually comparing output) is slow and inaccessible to a non-technical user.
The problem is therefore to provide a **live, interactive, decision-support twin** that
can inject incidents into a calibrated model and quantify their impact against a
baseline, in a form a non-specialist can operate and that an organisation could deploy.

## 1.3. Project Team

- **Developer / author:** [Name: to complete] — designed, implemented, tested and
  documented the solution (independent work).
- **Academic supervisor / examiner:** [to complete] — guidance and assessment.
- **Stakeholders / data providers (indirect):** Christchurch City Council and
  OpenStreetMap, whose open datasets calibrate the model.
- **AI assistant:** Claude Code (see Authorship Statement and §5.2).

---

# 2. REQUIREMENTS AND GOALS

## 2.1. Overview

**Overall goal:** deliver a decision-support digital twin of Christchurch's central-city
traffic that streams a calibrated simulation in real time, allows incident injection, and
measures the resulting impact against a baseline, backed by a cloud pipeline.

**Requirements / sub-goals and success metrics:**

| # | Requirement (sub-goal) | Success metric |
|---|---|---|
| R1 | Real-time data: emit vehicle state as JSON over WebSocket every simulation step | Live feed received by a browser client within milliseconds of each tick; unit-tested serialiser |
| R2 | Cloud pipeline: public WebSocket endpoint, metrics aggregation, time-series storage, as IaC | Live ticks reach InfluxDB Cloud via API Gateway + Lambda; all resources defined in Terraform |
| R3 | Live dashboard: map with speed-coloured vehicles, metric charts, pause/resume, hosted | Vehicles animate; three charts update live; dashboard deployable to S3/CloudFront + Pages |
| R4 | Decision support: inject an incident and compare it to a baseline with a quantified result | A baseline vs incident run produces a directionally-correct, quantified impact |
| R5 | Usability: operable by a non-technical user | Whole demo runs from the browser / one command, no command line required to operate |
| R6 | Engineering quality: tests, CI, reproducible packaging | Automated test suite green in CI; one-command Docker bring-up |

The original proposal set a 300-hour budget across three phases (real-time data; cloud
pipeline; live dashboard) plus an extension budget for five features (congestion alerts,
scenario comparison, historical replay, a threshold metrics panel, and Docker Compose).
Mid-project the extension work was **re-aimed from passive historical replay to active
what-if decision support** (see §5.1 and §3.3) — the defining purpose of a digital twin —
while retaining the real-data pipeline as the calibrated baseline.

## 2.2. Comparative Analysis

*(This extends/summarises the comparative study in the proposal. Please merge any
specific comparisons or citations from your proposal version.)*

- **Simulation engine.** SUMO (Lopez et al., 2018) was chosen over commercial
  microsimulators (e.g. Aimsun, PTV VISSIM) because it is open-source, scriptable through
  TraCI for real-time control, and already used for the existing Christchurch model.
  Mesoscopic/agent frameworks (e.g. MATSim) model demand well but are less suited to the
  tick-level, per-vehicle real-time streaming this project needs.
- **Digital-twin framing.** Rather than a purely descriptive dashboard of historical
  data, the project adopts a *decision-support* framing: perturb a calibrated model and
  measure impact. This is more defensible than estimating "real" conditions from sparse,
  peak-only survey counts on a schematic graph.
- **Time-series store.** InfluxDB (InfluxData, n.d.) was selected for tick data over
  general-purpose databases and over Prometheus (pull-based, ops-oriented) because it is
  purpose-built for high-frequency time series and has a free managed tier.
- **Cloud architecture.** A serverless design (API Gateway + Lambda) was chosen over
  always-on servers to minimise cost (near-zero idle) and to suit bursty, per-tick
  ingestion; Terraform provides reproducible, reviewable provisioning.
- **Deployment / packaging.** Docker Compose gives a portable one-command local demo, a
  right-sized alternative to a full container-orchestration platform for a project of
  this scale.

---

# 3. METHODS

## 3.1. Overview

The project followed an **iterative, milestone-driven** approach: each feature was built
as a small, independently testable increment, committed one logical step at a time on a
feature branch, and validated by unit tests before integration. A *pure-core / thin-glue*
design was used throughout — business logic in pure functions tested against fakes and
mocks, with thin I/O wrappers — so that correctness could be verified without SUMO, the
cloud, or a network. Progress, decisions and a running budget were tracked in-repository
(`CLAUDE.md`, `CHECKLIST.md`) and in weekly journals.

**Tools and technologies:** Python (asyncio, websockets, sumolib/TraCI); SUMO; InfluxDB;
AWS (API Gateway, Lambda, DynamoDB, S3, CloudFront, Secrets Manager, CloudWatch);
Terraform; Leaflet and Chart.js; Docker / Docker Compose; GitHub and GitHub Actions;
pytest + moto for testing.

## 3.2. Design

One **producer** (SUMO + the TraCI emitter) feeds one of two interchangeable
**pipelines** — a local InfluxDB stack or the AWS cloud stack — and a single HTML
**dashboard** points at whichever endpoints it is given (Figure 1).

![System architecture](img/architecture.png)

*Figure 1. System architecture. The producer (`run_traci.py --emit`) streams
vehicle-state JSON over WebSocket to the dashboard and, in parallel, to a local InfluxDB
pipeline and/or the AWS cloud pipeline; the dashboard reads history from the local replay
server or the cloud replay Lambda. Full data-flow, local and cloud deployment views and a
component/port reference are in the repository's `docs/ARCHITECTURE.md`.*

**Component interaction.** `run_traci.py` drives SUMO through TraCI and, each tick,
serialises vehicle state (converted to WGS84) and broadcasts it over WebSocket.
`metrics_writer.py` consumes that feed, computes per-tick metrics with the pure function
`compute_tick_metrics`, and writes them to InfluxDB tagged by `simId` and `scenario_id`.
The dashboard renders the live feed and queries history through a read endpoint
(`replay_server.py` locally, or a replay Lambda in the cloud). The **same**
`compute_tick_metrics` function is reused verbatim as the body of the cloud
`traffic-metrics` Lambda, so local and cloud produce identical metrics. Incidents are
injected by `incidents.py` (close edge/lane, speed limit, demand surge) with
apply-and-revert semantics; `control_server.py` lets a non-technical user start named
scenarios and inject incidents from the browser.

## 3.3. Risks and Challenges

| Risk / challenge | Impact | How it was handled |
|---|---|---|
| **Scope risk** — historical replay hard to defend as "real" | Could undermine the project's credibility | Pivoted the extension work to decision-support (what-if incidents) on the strong calibrated model; kept the real-data path as the baseline (logged in `CLAUDE.md`) |
| **SUMO installation** (no usable macOS binary; wrong PyPI packages) | Blocked local development | Built SUMO from source (documented recipe); used the official Ubuntu PPA in cloud/Docker |
| **Lambda Function URL returns 403 anonymously** | Hosted dashboard history could not read the cloud | Fronted the replay function with API Gateway instead of a public Function URL |
| **Local/cloud metric divergence** | Two code paths could drift | Extracted one pure `compute_tick_metrics` used by both the writer and the Lambda |
| **VM networking** (services unreachable through port-forwarding) | Local demo appeared broken | Bound servers to `0.0.0.0`; documented ports to forward; added Docker-permission guidance |
| **Secrets Manager destroy/apply conflict**, cost control | Could break redeploys or incur cost | Set zero recovery window; added a \$5 billing alarm and a cost-gated EC2 sim host |

## 3.4. Implementation

Development proceeded in the proposal's order and then through decision-support
increments:

1. **Real-time emitter** — `run_traci.py --emit` + `emitter.py` (asyncio WebSocket server,
   coordinate conversion, snapshot-on-connect, throttling).
2. **Cloud pipeline** — Terraform `infra/`: WebSocket API Gateway, three Lambdas
   (ingest/metrics/replay), DynamoDB connections table, S3 + CloudFront, Secrets Manager,
   CloudWatch + billing alarm; emitter cloud-forwarding mode (`--emit-target`).
3. **Dashboard** — extended `intersection_map.html` with the live layer, three Chart.js
   panels, pause/resume, and (later) the decision-support panels.
4. **Decision-support increments** — incident injection (`incidents.py`), scenario-tagged
   metrics + compare view, congestion-alert overlay, live click-to-inject with a
   Close↔Reopen toggle, an impact report, and GUI scenario control (`control_server.py`).
5. **Packaging & CI** — Docker Compose one-command stack (`docker-compose.yml`,
   `docker/`), one-command host launchers (`start_demo.sh`/`stop_demo.sh`), and GitHub
   Actions CI.

**Replicating the work.** The repository is self-contained: `git clone`, then
`docker compose up` builds and runs the whole stack locally (only Docker required), or
`start_demo.sh` runs it from host processes on a machine with Python + SUMO; the cloud
side is `terraform apply` in `infra/`. Step-by-step guides are in `DOCKER.md`,
`running_guide.md`, and `infra/README.md`.

**Artefacts produced.** The decision-support digital-twin system itself (the headline
artefact); ~33 Python modules; a ~1,600-line dashboard; 12 Terraform files + Lambda
functions; 91 unit tests; Docker/CI configuration; and layered documentation
(README, ARCHITECTURE, DOCKER, METRICS_REPLAY, running_guide, CHECKLIST, CLAUDE.md).

---

# 4. RESULTS AND OUTCOMES

## 4.1. Evidence of Deliverables

**Requirements met.** The table below maps the proposal's objectives to what was
delivered and the evidence for each.

| Objective | Status | Evidence |
|---|---|---|
| R1 — JSON/WebSocket emitter, every step, configurable rate | Met | `run_traci.py --emit`, `emitter.py`; 6 unit tests; verified live |
| R2 — API Gateway WebSocket endpoint | Met | `infra/api_gateway.tf`; verified end-to-end |
| R2 — Lambda metrics aggregation | Met | `traffic-metrics` λ = `compute_tick_metrics`; 6 tests |
| R2 — InfluxDB Cloud storage | Met | writes verified (local + cloud) |
| R2 — Infrastructure as code (Terraform) | Met | 12 `.tf` files, applied |
| R2 — GitHub Actions CI/CD | Met | `ci.yml`, 91 tests, Python 3.11 + 3.12 |
| R3 — WebSocket client + speed-coloured markers | Met | `intersection_map.html` |
| R3 — Three Chart.js panels | Met | count / avg speed / congestion |
| R3 — Pause/resume | Met | live control |
| R3 — Static hosting (S3/CloudFront + Pages) | Met | `cdn.tf`, `deploy-dashboard.yml` |
| Ext — Congestion alerts | Met | congestion overlay |
| Ext — Scenario comparison | Exceeded | compare view + impact report |
| Ext — Historical replay (scrub bar) | Deferred | superseded by the pivot; counts replay is the baseline |
| Ext — Threshold metrics panel | Folded | into the congestion overlay |
| Ext — Docker Compose | Met | `docker-compose.yml`, `docker/` |
| Beyond proposal | Added | incident injection, live click-to-inject + recovery, GUI scenario control, impact report, ETL baseline bridge, one-command launchers |

**Scenario results (objective measure of success).** The core test of the twin is whether
an injected incident produces a measurable, directionally-correct impact against the
calibrated baseline. Each scenario is run from the morning peak, its per-tick metrics
stored in InfluxDB tagged by `scenario_id`, and baseline-vs-incident deltas computed by
the dashboard impact report (and reproduced on the command line by
`scripts/capture_results.py`).

> **Note — to be populated from a run on the simulation host.** Values are placeholders
> («…»); run the three preset scenarios and paste the captured figures. The method,
> table and figure slots are in place so the evidence drops straight in.

**Table 1. Baseline vs incident impact (morning peak).**

| Scenario | Avg speed (km/h) | Δ speed | Congestion index | Δ congestion | Stopped (mean / peak) | Vehicles (mean) |
|---|---|---|---|---|---|---|
| Baseline (`baseline_am`) | «…» | — | «…» | — | «…» / «…» | «…» |
| Crash — arterial closed (`crash_arterial`) | «…» | «−…%» | «…» | «+…» | «…» / «…» | «…» |
| Roadworks — reduced speed (`roadworks`) | «…» | «−…%» | «…» | «+…» | «…» / «…» | «…» |

**Figures (screenshots to capture from the running dashboard; place in Appendix A if
large):**

- *Figure 2. Live dashboard — speed-coloured vehicles on the CBD map with the three live
  metric panels.*
- *Figure 3. Compare view — baseline vs incident overlaid for a metric, with the
  quantified summary line.*
- *Figure 4. Impact report — baseline-vs-incident table with directional deltas.*
- *Figure 5. Congestion-alert overlay — slow segments flagged red on the network.*

**How to produce the evidence.** With the stack running (`docker compose up`, or
`start_demo.sh`), start each preset from the dashboard, then run:

```
python scripts/capture_results.py --replay http://localhost:8788/metrics \
  --scenarios baseline_am,crash_arterial,roadworks
```

This prints Table 1 as Markdown (means, peaks, deltas vs baseline), ready to paste.

## 4.2. Testing / Validation

Testing used a **pure-core / thin-glue** strategy so logic is verified without external
systems:

- **91 unit tests**, all passing, run in CI on Python 3.11 and 3.12:
  - 46 core (`scripts/tests/`): incidents (14), control_server (11), emitter (6),
    metrics (6), capture_results (5), replay_server (4).
  - 45 ETL (`scripts/etl/tests/`): scenario bridge (9), counts ETL (7), ingest (7),
    query (6), drive client (6), lambda query (4), lambda ingest (3), s3 store (3).
- **Fakes and mocks:** a fake `traci`/`Popen` and `moto` (mock AWS) mean no SUMO, cloud,
  or network is needed to test.
- **Front-end:** the dashboard JavaScript is syntax-checked with `node --check`.
- **Continuous integration:** `.github/workflows/ci.yml` runs the full suite on every push
  and pull request; a second workflow publishes the dashboard to GitHub Pages.
- **End-to-end verification:** the live path (SUMO → emitter → writer → InfluxDB →
  dashboard) and the cloud path (→ API Gateway → Lambdas → InfluxDB Cloud) were each
  exercised and confirmed during development.

*(Evidence: CI run screenshots and a `pytest` summary can be added to Appendix A.)*

---

# 5. REFLECTIONS

## 5.1. Reflections

**Did I achieve what I set out to achieve?** Yes — the core objectives (real-time
emitter, cloud pipeline, live dashboard) were all met, the committed Milestone-5
engineering deliverables (Docker Compose + CI) were completed, and the extension work was
delivered as a stronger decision-support feature set.

**Did it go as expected?** Mostly, with one deliberate change: part-way through I judged
that replaying historical counts was hard to defend as "real", and re-aimed the extension
work at *what-if decision support* on the calibrated model, keeping the real-data
pipeline as a baseline. Making and defending that scope decision on engineering and
academic merit — not sunk cost — was the single most valuable lesson of the project.

**New learning.** I had to learn real-time control of SUMO through TraCI and asynchronous
streaming in Python; serverless AWS architecture and infrastructure-as-code with
Terraform (least-privilege IAM, secrets handling, cost controls); time-series modelling
in InfluxDB; containerisation with Docker Compose; and CI with GitHub Actions — most of
which were new to me at the start.

**Personal and technical growth.** Technically I moved from writing scripts to designing
a multi-component, cloud-connected system with a test strategy and reproducible
deployment. Personally I grew in planning and judgement — scoping increments, tracking a
budget, documenting honestly (including limitations), and communicating decisions.

## 5.2. Use of Generative AI

Generative AI (Claude Code, Anthropic) was used substantially across the technical work:
drafting and refactoring code, generating unit tests, scaffolding Terraform and Docker
configuration, producing diagrams and documentation, and drafting this report from
project artefacts. I directed the work (goals, architecture and design decisions),
reviewed and validated all generated code and prose, and ran and verified the tests and
the running system.

**Where it helped:** it accelerated boilerplate (IaC, test fixtures, glue code),
surfaced options quickly, and kept documentation in step with the code.

**Issues it caused / that I had to manage:** generated code and text required careful
review — it could be confidently wrong, make assumptions about the environment, or need
correcting for this project's specifics (e.g. SUMO/AWS quirks). I treated its output as a
draft to verify, not a finished answer, and relied on the test suite and end-to-end runs
as the source of truth.

*(Please confirm this reflects your actual usage and edit to your voice before
submission.)*

## 5.3. Conclusions

**Strengths.** A working, tested, reproducibly deployable decision-support twin: it runs
in real time, lets a non-technical user inject incidents and read a quantified impact,
and can be stood up with one command locally or deployed to AWS as code. The honest
framing (synthetic incidents on a calibrated baseline) is defensible, and quality
engineering (91 tests, CI, IaC, layered docs) supports it.

**Limitations.** Incidents are synthetic (no live sensor feed); a "closed" edge caps
speed rather than rerouting traffic, so vehicles queue rather than divert; live
click-to-inject works only over the local WebSocket (not yet over the hosted cloud
dashboard); and the Docker simulation image has been configuration-validated but not yet
built and run on the deployment VM.

**Suggestions for the future.** Incident rerouting/detours; a cloud control path so the
hosted dashboard is fully interactive; an enhanced impact report (true per-vehicle delay
via `getTimeLoss`, affected-area, recovery-time); and load/performance testing.

**What I would do differently.** Capture quantified scenario results earlier (rather than
at the end), and stand up the hosted deployment continuously instead of in a final push —
both would have provided evidence to iterate against sooner.

---

# 6. REFERENCES

*Referencing follows APA 7th edition (Lincoln University Learning, Teaching & Library
guidance: https://ltl.lincoln.ac.nz/learning-and-research-skills/writing-and-referencing/referencing/).*

Agafonkin, V. (n.d.). *Leaflet: An open-source JavaScript library for mobile-friendly
interactive maps*. Retrieved October 12, 2026, from https://leafletjs.com/

Amazon Web Services. (n.d.). *AWS documentation*. Retrieved October 12, 2026, from
https://docs.aws.amazon.com/

Chart.js contributors. (n.d.). *Chart.js documentation*. Retrieved October 12, 2026, from
https://www.chartjs.org/docs/latest/

Christchurch City Council. (n.d.). *Intersection traffic counts database*. Retrieved
October 12, 2026, from https://ccc.govt.nz/transport/improving-our-transport-and-roads/traffic-count-data/intersection-traffic-counts-database

Docker, Inc. (n.d.). *Docker documentation*. Retrieved October 12, 2026, from
https://docs.docker.com/

German Aerospace Center (DLR). (n.d.). *SUMO documentation*. Retrieved October 12, 2026,
from https://sumo.dlr.de/docs/

HashiCorp. (n.d.). *Terraform documentation*. Retrieved October 12, 2026, from
https://developer.hashicorp.com/terraform/docs

InfluxData. (n.d.). *InfluxDB OSS documentation*. Retrieved October 12, 2026, from
https://docs.influxdata.com/influxdb/v2/

Lopez, P. A., Behrisch, M., Bieker-Walz, L., Erdmann, J., Flötteröd, Y.-P., Hilbrich, R.,
Lücken, L., Rummel, J., Wagner, P., & Wießner, E. (2018). Microscopic traffic simulation
using SUMO. In *2018 21st International Conference on Intelligent Transportation Systems
(ITSC)* (pp. 2575–2582). IEEE. https://doi.org/10.1109/ITSC.2018.8569938

OpenStreetMap contributors. (n.d.). *OpenStreetMap*. Retrieved October 12, 2026, from
https://www.openstreetmap.org/

---

# 7. APPENDICES

## Appendix A — Independent Software Project

**GitHub Repository:** https://github.com/kyawzinmyolwin/demo_smart_city_digital_twin

**URL for the Deployed App:** [to complete — hosted CloudFront dashboard URL once the
hosted deploy is finished; see §5.3 limitations]

*Supplementary evidence to attach here (optional): dashboard screenshots (Figures 2–5),
a CI run summary, and the `scripts/capture_results.py` output for Table 1.*
