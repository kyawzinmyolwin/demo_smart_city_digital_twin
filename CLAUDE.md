# CLAUDE.md — demo_smart_city_digital_twin

Project context for Claude Code. Read this before touching any file.

---

## What this project is

A Christchurch CBD traffic simulation (SUMO-based) extended with a cloud data pipeline and a live browser dashboard. The simulation already exists and works. Everything cloud-related is new — nothing has been built yet.

**Repo:** `kyawzinmyolwin/demo_smart_city_digital_twin`
**Student:** Lincoln University, NZ — COMP 693 Industry Project
**Budget:** 300 hours total (200h core build + 100h extension features)
**Cloud platform:** AWS (primary choice)

---

## What already exists — do not modify these

### Simulation core (complete, production-quality)
- `smart_city_digital_twin/2D_simulation/Christchurch_Central_City_main_streets.sumocfg` — main SUMO config
- `smart_city_digital_twin/2D_simulation/data/output/network/` — road network built from real Christchurch City Council + OpenStreetMap data
- `smart_city_digital_twin/2D_simulation/data/output/demand/traffic_trips.routed.rou.xml` — vehicle demand from real Miovision traffic counts
- `smart_city_digital_twin/2D_simulation/scripts/sim_pipeline.py` — 4000+ line core library, do not touch
- `smart_city_digital_twin/3D_simulation/` — Unity 3D twin, out of scope for this project

### Existing scripts to extend (not rewrite)
- `smart_city_digital_twin/2D_simulation/scripts/run_traci.py` — TraCI control loop. Currently steps the simulation and prints status to console only. **This is the first file to extend.**
- `smart_city_digital_twin/2D_simulation/scripts/intersection_map.html` — Leaflet map of intersections. Loads a static CSV once. **This is the frontend to extend.**

### What run_traci.py currently does
Connects to SUMO via TraCI on port 8813. Jumps to sim time 23400s (06:30). Steps the simulation in a `while True` loop. Calls `_print_status()` every 60 sim seconds — this just prints to terminal. No JSON output, no WebSocket, no data persistence. The per-step hook is here:

```python
traci.simulationStep()
if int(t) % 60 == 0:
    _print_status(traci)
```

This is where the emitter call goes.

### What intersection_map.html currently does
A Leaflet map centred on Christchurch CBD (-43.53, 172.636). Fetches `../data/output/intersection_geo.csv` once on load and renders 96 intersection nodes and their directional links. No WebSocket client. No vehicle layer. No live data of any kind. Uses Leaflet 1.9.4 from CDN.

---

## What we are building — in order

### Phase 1: JSON emitter + WebSocket server (first task)
Extend `run_traci.py` to emit vehicle state as JSON over WebSocket every simulation step.

**Target JSON schema:**
```json
{
  "tick": 1720123456789,
  "simId": "christchurch-cbd-001",
  "simTime": 23460.1,
  "vehicleCount": 214,
  "vehicles": [
    {
      "id": "veh_001",
      "lat": -43.5321,
      "lng": 172.6362,
      "speed": 13.4,
      "lane": "edge_42_0",
      "accel": 0.2
    }
  ]
}
```

**Implementation notes:**
- SUMO XY coordinates must be converted to WGS84 lat/lon using `sumolib.net.convertXY2LonLat()` — the net file is at `data/output/network/Christchurch_Central_City_main_streets.net.xml`
- Use `asyncio` + `websockets` library for the WebSocket server
- Run the WebSocket server and TraCI loop concurrently — asyncio event loop wrapping the sync TraCI calls
- Server listens on port 8765
- Emit every step (not just every 60s) when clients are connected
- Send a snapshot of current state to any new client on connect (don't wait for next tick)
- Configurable tick rate via `--emit-interval` arg (default: every step)
- Unit test the JSON serialiser independently from the TraCI connection

### Phase 2: Cloud data pipeline
- AWS API Gateway (WebSocket API) as the public-facing endpoint
- AWS Lambda for metrics aggregation per tick (flow, avg speed, congestion index)
- InfluxDB Cloud (free tier) for time-series storage
- Infrastructure as code: AWS CDK or Terraform
- GitHub Actions CI/CD pipeline

### Phase 3: Live dashboard (extends intersection_map.html)
- Add WebSocket client to existing Leaflet map
- Animated vehicle markers — colour-coded by speed (green/amber/red)
- 3 Chart.js panels: vehicle count, avg speed, density over time
- Pause/resume button calling the API
- Deploy static HTML/JS to GitHub Pages or S3+CloudFront

### Extension features (after core build, ~100h budget)
1. Congestion alerts — flag segments where avg speed < threshold for N consecutive ticks
2. Scenario comparison — two parallel SUMO runs tagged by scenario_id, metrics shown side by side
3. Historical replay — scrub bar querying time range from InfluxDB, playback at variable speed
4. Threshold metrics panel — Chart.js threshold lines showing normal vs congested ranges
5. Docker Compose — one command brings up sim + API server + DB

---

## Key technical decisions (already made, do not relitigate)

| Decision | Choice | Reason |
|---|---|---|
| Cloud platform | AWS | Better WebSocket API Gateway free tier, larger NZ community |
| Real-time framing | Simulation output only | CCC data sources are historical download-only, not live sensors |
| Frontend base | Extend intersection_map.html | Already has working Leaflet setup for Christchurch CBD |
| Containerisation | Docker + Docker Compose | Right-sized for this project; Kubernetes is a stretch-goal only |
| Time-series store | InfluxDB Cloud (free tier) | Designed for tick data; free tier sufficient for prototype |
| CI/CD | GitHub Actions | Already using GitHub; most NZ employers recognise it |

---

## Data sources (context only — no code changes needed)

- **CCC Intersection Traffic Counts** — historical Miovision survey data, download-only, no API. Already parsed by `traffic_counts_parser.py`. Used to build demand, not streamed live.
- **CCC ArcGIS Hub** — intersection geometry. Has a REST API (`gis.ccc.govt.nz/arcgis/rest/services/OpenData`) but used as a one-time calibration source. The downloaded `intersection_geo.csv` is what the map reads.
- **SUMO via TraCI** — the actual real-time data source. Every simulation step produces fresh vehicle state.

---

## Project structure (current)

```
demo_smart_city_digital_twin/
├── CLAUDE.md                          ← this file
├── Unity_fundamental/                 ← unrelated tutorial project, ignore
└── smart_city_digital_twin/
    ├── README.md
    ├── 2D_simulation/
    │   ├── Christchurch_Central_City_main_streets.sumocfg
    │   ├── requirements.txt
    │   ├── data/
    │   │   ├── input/                 ← source data (Miovision, OpenData)
    │   │   └── output/
    │   │       ├── network/           ← .net.xml files
    │   │       ├── demand/            ← .rou.xml files
    │   │       └── intersection_geo.csv
    │   └── scripts/
    │       ├── run_traci.py           ← EXTEND THIS FIRST
    │       ├── sim_pipeline.py        ← do not modify
    │       ├── intersection_map.html  ← EXTEND FOR DASHBOARD
    │       └── [other pipeline scripts — do not modify]
    └── 3D_simulation/                 ← Unity project, out of scope
```

---

## Environment setup

```bash
cd smart_city_digital_twin
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r 2D_simulation/requirements.txt
pip install websockets asyncio     # new dependencies for emitter
```

SUMO must be installed and on PATH. Project tested with SUMO 1.27.1 (also fine for the
1.26 target — no config changes needed between them).
SUMO_HOME must be set (e.g. `C:\Sumo` on Windows or `/usr/share/sumo` on Linux).

Run existing simulation to confirm it works before touching anything:
```bash
cd smart_city_digital_twin/2D_simulation
sumo-gui -c Christchurch_Central_City_main_streets.sumocfg
```

### macOS setup (this machine, verified 2026-07-15)

The `dlr-ts/sumo` Homebrew tap is dead — its formula uses a removed Homebrew API
(`cxxstdlib_check`) and fails to install on current Homebrew. conda-forge's `sumo`
package and PyPI's plain `sumo` package are also **not** this project's SUMO — they're
an unrelated materials-science bandstructure tool. The real package on PyPI is
`eclipse-sumo`, but it only ships up to 1.20.0 and needs exact-version system libs
(xerces-c 3.2, proj 25, FOX 1.6) that are painful to match by hand.

**What actually works: build from source.**

1. Download the source tarball from https://sumo.dlr.de/docs/Downloads.php (there is
   no signed macOS binary/installer — source is the only macOS-relevant download) and
   extract it, e.g. to `~/sumo/sumo-1.27.1`.
2. Install build deps via Homebrew: `brew install cmake xerces-c proj`.
3. Headless build (no GUI, no Xcode needed — this is all `run_traci.py` / TraCI
   control needs):
   ```bash
   cd ~/sumo/sumo-1.27.1
   mkdir -p build/cmake-build-headless && cd build/cmake-build-headless
   cmake ../.. -DCMAKE_BUILD_TYPE=Release
   cmake --build . --target sumo netconvert duarouter netgenerate od2trips \
     jtrrouter marouter activitygen polyconvert dfrouter -j$(sysctl -n hw.ncpu)
   ```
   Binaries land in `~/sumo/sumo-1.27.1/bin/`. Confirm the "Enabled features" cmake
   log line does *not* mention GUI — that's what avoids the dependency chain below.
4. Set in `~/.bash_profile` (or shell equivalent):
   ```bash
   export SUMO_HOME="$HOME/sumo/sumo-1.27.1"
   export PATH="$SUMO_HOME/bin:$PATH"
   ```
5. `run_traci.py --no-gui` is the flag to use — the script defaults to `--gui`, which
   needs the GUI build below.

**Adding `sumo-gui` without installing full Xcode:**

Homebrew's `fox` formula (SUMO's GUI toolkit) depends on `mesa`, and current `mesa`
(post–Dec 2023) hard-depends on `molten-vk`, which refuses to build without a full
Xcode.app install (Command Line Tools alone aren't enough) — a non-starter if you're
not upgrading Xcode/macOS. The fix: `mesa` had a bottled, Xcode-free formula revision
right up until that dependency was added. Pin to it via a throwaway local tap:

```bash
brew tap-new local/legacy-gl
TAP=/usr/local/Homebrew/Library/Taps/local/homebrew-legacy-gl/Formula
curl -s https://raw.githubusercontent.com/Homebrew/homebrew-core/83d2ce266d/Formula/m/mesa.rb -o "$TAP/mesa.rb"
curl -s https://raw.githubusercontent.com/Homebrew/homebrew-core/190c1da9ec/Formula/m/mesa-glu.rb -o "$TAP/mesa-glu.rb"
curl -s https://raw.githubusercontent.com/Homebrew/homebrew-core/f6f5852d56716a3f288dde936c47b855f91fbcd0/Formula/fox.rb -o "$TAP/fox.rb"
```

Then edit those three files:
- In `mesa.rb`: delete the `:build`-only deps (`bison`, `meson`, `ninja`, `pkg-config`,
  `pygments`, `python-mako`, `python-setuptools`, `python@3.12`, `xorgproto`) — they've
  since been renamed/removed upstream and aren't needed since we're installing from
  the bottle, not compiling.
- In `mesa-glu.rb`: replace `depends_on "meson"/"ninja"/"pkg-config" => :build` and
  `depends_on "mesa"` with just `depends_on "local/legacy-gl/mesa"` (otherwise Homebrew's
  solver pulls the *current* `mesa` — the one needing `molten-vk` — as the dependency).
- In `fox.rb`: replace `depends_on "mesa"` / `"mesa-glu"` with
  `depends_on "local/legacy-gl/mesa"` / `"local/legacy-gl/mesa-glu"` for the same reason.

Then:
```bash
brew install local/legacy-gl/mesa local/legacy-gl/mesa-glu local/legacy-gl/fox
```
All three pour from prebuilt `ventura` bottles — no compiling, no Xcode.

Rebuild SUMO with GUI enabled (same source tree, a separate build dir so the headless
one is untouched):
```bash
cd ~/sumo/sumo-1.27.1
mkdir -p build/cmake-build-gui && cd build/cmake-build-gui
cmake ../.. -DCMAKE_BUILD_TYPE=Release   # "Enabled features" line should now say GUI
cmake --build . --target sumo-gui -j$(sysctl -n hw.ncpu)
```
`sumo-gui` lands in the same `~/sumo/sumo-1.27.1/bin/` (SUMO's CMake install rule
targets the source tree's top-level `bin/` regardless of build dir).

**Running `sumo-gui`:** this FOX build is X11-based, not native Cocoa, so it needs
XQuartz as a display server (`brew install --cask xquartz` — this step needs an
interactive sudo password, so run it yourself in a real terminal, not through an
agent's non-interactive shell):
```bash
open -a XQuartz        # start the X server once per login (or set it to auto-launch)
export DISPLAY=:0
sumo-gui -c Christchurch_Central_City_main_streets.sumocfg
```

Sanity checks after setup:
```bash
sumo --version && sumo-gui --version
python3 -c "import sys,os; sys.path.insert(0, os.environ['SUMO_HOME']+'/tools'); import sumolib, traci; print('OK')"
python3 scripts/run_traci.py --no-gui --jump-to 23400 --end 23430   # real TraCI run
```

---

## Where to start — first task

**Add a JSON emitter to `run_traci.py`.**

Specifically:
1. Load the SUMO net file with `sumolib` to get the coordinate converter
2. Write a `serialize_vehicles(traci, net)` function that returns the JSON schema above
3. Write an async WebSocket server using `websockets` that broadcasts to all connected clients
4. Wrap the existing synchronous TraCI loop so it runs inside an asyncio event loop
5. Call `serialize_vehicles()` each step and broadcast if any clients are connected
6. Add `--emit-interval SEC` argument (default 1 step, i.e. every step)
7. Write a unit test for `serialize_vehicles()` using a mock traci object

Do not change the existing TraCI connection logic, argument parser structure, or `_print_status` function. Add alongside, do not replace.

---

## Coding conventions (match existing repo style)

- Python 3.10+ type hints where the existing code uses them
- `from __future__ import annotations` at top (existing pattern)
- Argparse for all CLI arguments (existing pattern)
- No f-string format for SUMO commands — use list concatenation (existing pattern)
- Keep new functions at module level, not nested inside `main()`
- One commit per logical step

---

## What "real-time" means in this project

The simulation generates fresh vehicle position and speed data every step. The emitter pushes that data to connected clients within milliseconds of each step completing. That pipeline latency is what "real-time" refers to — not live sensor feeds from physical Christchurch roads. The council data sources are historical calibration inputs, used once at setup time.
