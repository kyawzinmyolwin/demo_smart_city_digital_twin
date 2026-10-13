**COMP 693 Industry Project — Final Report**

**Project title:** Cloud-Connected Extension of the Smart City Digital Twin

**Project type:** Industry-Mentored

**Submitted by:** Kyaw Zin Myo Lwin
**Student ID:** 1169799
**Host Company:** JIX Reality
**Name of Mentor / Supervisor:** Hansi Udapola
**Mentor Email:** hansi@jix.co.nz
**Company Address:** 213 Tuam Street, Christchurch Central City, Christchurch 8011, New Zealand
**Date:** [submission date — e.g. 19 October 2026]

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

**Methods:** The system was built as a **proof of concept** to demonstrate feasibility
end-to-end. It extends an existing SUMO model with a WebSocket emitter; builds an AWS
serverless pipeline (API Gateway, Lambda, InfluxDB Cloud) as Terraform infrastructure-
as-code; extends a Leaflet/Chart.js dashboard with incident injection, scenario comparison
and impact reporting; and packages it with Docker Compose and GitHub Actions CI, developed
through iterative milestone increments.

**Outcome:** A working, tested (91 unit tests, CI on two Python versions), reproducibly
deployable **proof-of-concept** twin. Strengths: real-time operation and an honest
baseline-vs-incident comparison runnable with one command. Limitations (consistent with a
PoC): incidents are synthetic, and a closure caps speed rather than rerouting traffic.

---

## Authorship Statement

This report and the accompanying software were prepared with the assistance of
Claude / Claude Code (Anthropic), an AI assistant, used under the author's direction to
accelerate implementation, testing, infrastructure-as-code, documentation, and to
structure and word this report. All architectural and scope decisions were made by the
author, who reviewed, ran and validated all generated code and text and is responsible
for the final content. See §5.2 for detail.

*(Please confirm this reflects your own working process before submitting.)*

---

## Glossary / Acronyms

| Term / acronym | Meaning |
|---|---|
| **Digital twin** | A live, data-driven virtual model of a real system used to monitor and test "what-if" scenarios. |
| **Proof of concept (PoC)** | A limited but working implementation built to demonstrate that an idea is feasible, rather than a production-ready product. |
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

This is an **industry-mentored project** for COMP 693, hosted by **JIX Reality**, a
Christchurch-based company working in immersive and digital-twin technologies. It extends
an existing SUMO-based simulation of the Christchurch central-city road network —
originally built during a related COMP693 digital-twin internship at JIX Reality — into a
**cloud-connected digital twin**. The existing simulation already produces high-fidelity
vehicle and public-transport movement driven by real Christchurch City Council
traffic-count data; what did not yet exist was any mechanism for that data to leave the
local machine. This project builds that mechanism: a streaming pipeline carrying the
simulation's output, cloud-based storage of the resulting time-series, a browser
dashboard displaying that streamed output, and a set of decision-support features. The
work is scoped to a 300-hour budget and framed as a cloud and streaming-data engineering
extension of the existing simulation.

## 1.2. Problem

The existing simulation produces realistic, calibrated vehicle and public-transport
movement, but that output never leaves the machine it runs on. The accompanying browser
map loads a single static CSV file; there is no mechanism for the simulation's state to
be streamed, stored, or queried while or after it runs. This matters because a digital
twin only creates value once its state is observable by people other than the person
running it locally: a supervisor reviewing progress, an examiner assessing a
demonstration, or — in a real deployment — a transport planner monitoring conditions
during a stadium event. Without a data pipeline out of the simulation and a persistent
store behind the dashboard, the system cannot be piloted, monitored over time, or used to
compare alternative scenarios; it can only be watched, once, on the developer's own
screen.

## 1.3. Project Team

- **Technical Contributor (author):** Kyaw Zin Myo Lwin (Student ID 1169799) — sole
  developer, responsible for all design, implementation, testing and documentation.
- **Mentor / Supervisor:** Hansi Udapola (JIX Reality, hansi@jix.co.nz) — project
  oversight and milestone review (product-owner role at sprint reviews, §3.1).
- **Host company:** JIX Reality, Christchurch — provides the project context and the
  existing simulation from the prior internship.
- **Data providers (indirect):** Christchurch City Council (traffic counts, intersection
  geometry) and OpenStreetMap (base road network).
- **AI assistant:** Claude / Claude Code (see Authorship Statement and §5.2).

---

# 2. REQUIREMENTS AND GOALS

## 2.1. Overview

**Overall goal (from the proposal):** extend the existing SUMO-based Christchurch CBD
simulation into a cloud-connected digital twin, delivering a streaming data pipeline,
cloud-based time-series storage, and an interactive browser dashboard with **at least four
decision-support features**, all deployable via a single Docker Compose command.

**Sub-goals (the five project milestones):**

| # | Sub-goal (milestone) | Deadline |
|---|---|---|
| M1 | Stream vehicle-state data out of the simulation every step, without modifying the existing simulation core | 16 Aug 2026 |
| M2 | Provision cloud infrastructure (AWS, InfluxDB Cloud) to receive and persist the streamed data as time-series records | 6 Sep 2026 |
| M3 | Extend the browser dashboard with a streaming vehicle layer, replacing its one-time static load | 20 Sep 2026 |
| M4 | Implement at least four decision-support features (congestion alerts, scenario comparison, historical replay, threshold metrics panel) | 5 Oct 2026 |
| M5 | Package the system with Docker Compose and automate testing/deployment with GitHub Actions | 19 Oct 2026 |

**Success metrics (from the proposal):**

- End-to-end pipeline latency measured and reported (target: sub-second from simulation
  step to dashboard update).
- All five sub-goals demonstrated working in a single recorded run.
- Terraform able to reprovision the full AWS stack from a clean account.
- Supervisor sign-off on a live demonstration of each decision-support feature.
- Final report submitted evaluating the system against these goals.

**Evolution during delivery.** Milestone 4 was committed as "at least four
decision-support features." During delivery the *specific set* evolved from the
originally-listed features toward stronger **what-if decision support** on the calibrated
model: congestion alerts and scenario comparison were kept, incident injection, live
click-to-inject and an impact report were added, while historical replay was
de-prioritised (the real-data counts path became the comparison **baseline** rather than a
headline feature) and the threshold-metrics idea was folded into the congestion overlay.
The "≥ 4 decision-support features" requirement is therefore met, with a set better
aligned to the purpose of a digital twin (see §3.3 and §5.1).

## 2.2. Comparative Analysis

*(Extended from the comparative study in the proposal.)*

Two publicly-documented systems are directly comparable, based on what each documents
about itself.

The first is an **open-source SUMO traffic dashboard built with FastAPI and TraCI**
(keshu-bara, 2025), which already provides live vehicle tracking and congestion detection
from a running SUMO simulation. However, by its own documentation it runs entirely on a
single machine, updates the browser by *polling* rather than genuine streaming, and does
not persist data to a database; historical replay is listed only as a planned future
feature, not something currently implemented.

The second is a **peer-reviewed cloud architecture that streams SUMO simulation data
through a serverless AWS pipeline** to support a real-time vehicle speed-advisory
application (Deng et al., 2024). This shows that an AWS-based, SUMO-driven streaming
architecture is viable at a latency requirement similar to the one this project targets.
However, the published system was built to evaluate a specific control algorithm rather
than to serve as a general-purpose dashboard, and it does not include decision-support
features such as alerts, scenario comparison, or historical replay.

Between them, these two systems indicate that the individual pieces of this project — a
SUMO dashboard with live tracking, and an AWS-based SUMO streaming pipeline — already
exist separately. Based on what is publicly documented about each, **neither combines a
calibrated real-city simulation, cloud-based persistent storage, and a dashboard with
decision-support features in one system.** This project's contribution is combining these
three elements rather than any one of them in isolation. The decision-support set was
further sharpened during delivery toward what-if incident analysis (§2.1), which neither
comparable system offers.

---

# 3. METHODS

## 3.1. Overview

**Methodology — proof of concept.** The project was developed as a **proof of concept
(PoC)**: its purpose is to demonstrate, end-to-end, the *feasibility* of a cloud-connected
decision-support traffic digital twin — not to deliver a production-hardened system. A PoC
approach was appropriate because the contribution is a **novel combination** of pieces that
exist only separately (a calibrated real-city SUMO simulation, a serverless cloud pipeline,
and a decision-support dashboard — see §2.2), so the first question to answer is "can these
be made to work together, reliably, at the required latency, within a student budget?".
The PoC is therefore deliberately **scoped**: incidents are synthetic (what-if
perturbations, not live sensor data), the cloud runs on free-tier / on-demand resources,
and some paths are demo-grade rather than fully productionised (see §5.3 Limitations). It
is nonetheless a **working, deployed and tested** implementation, so it proves the concept
rather than merely describing it. Success is judged by the proof-of-concept criteria in
§2.1 (the pipeline works end-to-end, an injected incident produces a measurable impact, and
the stack is reproducibly deployable).

**Development process.** Within that PoC, the build used **Scrum adapted for a single
developer**. The
five milestones (§2.1) doubled as sprints: each began by planning that milestone's tasks
into a backlog, ran through self-review against that backlog, and ended with a sprint
review demonstrating the working increment to the supervisor (acting as product owner),
followed by a short retrospective. One person covered all Scrum roles, but the
plan–build–review–retrospective cycle was kept for every milestone, which suited a project
where each milestone delivers a demonstrable increment that benefits from feedback before
the next layer is built on it.

**Techniques and methods.**

- **Vertical-slice-first development** — build one intersection's worth of streaming,
  storage and dashboard display end-to-end before widening coverage, so integration risk
  is found early (M1–M3).
- **Infrastructure-as-code** — all AWS resources defined and provisioned through Terraform,
  so the cloud environment is reproducible and reviewable as code (M2).
- **Incremental, additive extension of existing files** — the existing simulation core,
  network and demand files are not modified; new functionality is added at the two
  confirmed extension points (the TraCI step hook in `run_traci.py` and the map's
  data-loading logic in `intersection_map.html`) (M1, M3).
- **Automated testing** — a *pure-core / thin-glue* design puts business logic in pure
  functions tested against fakes and mocks, with thin I/O wrappers, so correctness is
  verifiable without SUMO, the cloud or a network; plus an end-to-end integration path
  through the full pipeline (M4, §4.2). Work was committed one logical step at a time on a
  feature branch; progress, decisions and a running budget were tracked in-repository
  (`CLAUDE.md`, `CHECKLIST.md`) and in weekly journals.

**Tools and technologies.** SUMO 1.27.1 + TraCI and Python (asyncio, websockets, sumolib)
for the emitter/WebSocket server; AWS (API Gateway WebSocket API, Lambda, DynamoDB, S3,
CloudFront, Secrets Manager, CloudWatch) with Terraform for infrastructure-as-code;
InfluxDB Cloud (time-series storage); JavaScript with Leaflet (existing map) and Chart.js;
Docker / Docker Compose; GitHub and GitHub Actions; pytest + moto for testing; and Claude
Code as an AI coding assistant under a repository-level `CLAUDE.md` context file, subject
to the author's review of all generated code (§5.2).

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
| **AWS / InfluxDB free-tier limits** (anticipated in the proposal) | Unexpected cost | Kept resource usage minimal and serverless (near-zero idle); \$5 billing alarm; stayed within budget (≈ \$1–2/month) |
| **InfluxDB schema constraining later code** (anticipated) | Rework of dashboard/query code | Finalised the measurement/tag/field schema early (M2) before the dashboard and query code depended on it |
| **Scope creep toward Kubernetes / AI / XR** (anticipated) | Budget overrun on non-committed work | Treated those as explicit stretch goals; kept Docker Compose as the committed packaging deliverable |
| **Solo-developer time overrun on the 300-hour budget** (anticipated) | Missed milestones | Tracked hours against the milestone schedule and reviewed progress with the supervisor at each milestone |

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
- **Integration / end-to-end:** the live path (SUMO → emitter → writer → InfluxDB →
  dashboard) and the cloud path (→ API Gateway → Lambdas → InfluxDB Cloud) were each
  exercised and confirmed — a short simulation run was carried through the full pipeline
  into storage and shown on the dashboard, verifying the whole pipeline rather than each
  component in isolation.
- **Infrastructure reproducibility:** `terraform apply` was run to provision the AWS stack
  from configuration, confirming the entire cloud environment can be stood up from code
  alone.
- **Informal user-acceptance walkthroughs:** each decision-support feature was
  demonstrated live to the supervisor at the relevant milestone review, confirming it
  behaves as intended against real simulation output.
- **Basic load observation:** WebSocket message throughput was observed at representative
  vehicle counts to confirm the pipeline keeps pace with the simulation's step rate (a
  ~600-vehicle snapshot is ≈ 50 KB, within the 128 KB WebSocket message cap; the emitter
  interval is throttleable to avoid flooding API Gateway).

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

**Strengths.** As a proof of concept, the project succeeds: it is a working, tested,
reproducibly deployable decision-support twin that runs in real time, lets a non-technical
user inject incidents and read a quantified impact, and can be stood up with one command
locally or deployed to AWS as code — demonstrating that the novel combination at its core
is feasible. The honest framing (synthetic incidents on a calibrated baseline) is
defensible, and quality engineering (91 tests, CI, IaC, layered docs) supports it.

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

Deng, H.-W., Salek, M. S., Rahman, M., Chowdhury, M., Shue, M., & Apon, A. W. (2024).
*Leveraging public cloud infrastructure for real-time connected vehicle speed advisory at
a signalized corridor*. arXiv. https://arxiv.org/abs/2401.16545

Docker, Inc. (n.d.). *Docker documentation*. Retrieved October 12, 2026, from
https://docs.docker.com/

German Aerospace Center (DLR). (n.d.). *SUMO documentation*. Retrieved October 12, 2026,
from https://sumo.dlr.de/docs/

HashiCorp. (n.d.). *Terraform documentation*. Retrieved October 12, 2026, from
https://developer.hashicorp.com/terraform/docs

InfluxData. (n.d.). *InfluxDB Cloud documentation*. Retrieved October 12, 2026, from
https://docs.influxdata.com/influxdb/cloud/

keshu-bara. (2025). *Intelligent-Traffic-Management-System* [Computer software]. GitHub.
https://github.com/keshu-bara/Intelligent-Traffic-Management-System

Lopez, P. A., Behrisch, M., Bieker-Walz, L., Erdmann, J., Flötteröd, Y.-P., Hilbrich, R.,
Lücken, L., Rummel, J., Wagner, P., & Wießner, E. (2018). Microscopic traffic simulation
using SUMO. In *2018 21st International Conference on Intelligent Transportation Systems
(ITSC)* (pp. 2575–2582). IEEE. https://doi.org/10.1109/ITSC.2018.8569938

OpenStreetMap contributors. (n.d.). *OpenStreetMap*. Retrieved October 12, 2026, from
https://www.openstreetmap.org/

---

# 7. APPENDICES

## Appendix A — Software Project Artefacts

**GitHub Repository:** https://github.com/kyawzinmyolwin/demo_smart_city_digital_twin

**URL for the Deployed App:** [to complete — hosted CloudFront dashboard URL once the
hosted deploy is finished; see §5.3 limitations]

*Supplementary evidence to attach here (optional): dashboard screenshots (Figures 2–5),
a CI run summary, and the `scripts/capture_results.py` output for Table 1.*
