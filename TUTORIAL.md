# Tutorial: Smart City Digital Twin (Christchurch Traffic Simulation)

## 1. Project Overview

This repository (`COMP693_26S1_Project_Yun`) is a **traffic digital twin of Christchurch's central city**, built for a university industry project (COMP 693, Lincoln University / Jix Reality). It has two coupled parts:

- **2D simulation** — a microscopic traffic simulation built with **Eclipse SUMO** (Simulation of Urban MObility), driven by real Christchurch intersection/street data.
- **3D simulation** — a **Unity** scene that renders the same simulation in 3D, receiving live vehicle positions from SUMO over the **TraCI** protocol (SUMO's TCP-based remote-control API).

A Python "data pipeline" (in `2D_simulation/scripts/`) turns raw traffic-count spreadsheets and OpenData intersection files into the SUMO network/route files that both the 2D and 3D simulations consume.

There's also an unrelated `Unity_fundamental/` folder at the repo root — a separate, smaller Unity learning exercise (cube spawning/pooling). It is not part of the digital-twin workflow; this tutorial focuses on `smart_city_digital_twin/`.

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Traffic simulation engine | Eclipse SUMO (tested with 1.26, requires 1.20+) |
| Simulation ↔ 3D bridge | TraCI protocol over TCP (port 8813 by default) |
| 3D renderer / game engine | Unity **6000.3.11f1** (Unity 6), URP render pipeline, C# scripts, custom TraCI client library (`TraciLibrary/`) |
| Data pipeline | Python 3.10+, `openpyxl`/`xlrd` (Excel parsing), `pyproj` (NZTM↔WGS84 coordinate conversion) |
| Map visualization (optional) | Static HTML + Leaflet.js, served via Python's built-in HTTP server |

There is no web backend, database, or Node.js stack here — this is a simulation/desktop project, not a web app.

## 3. Repository Structure

```
demo_smart_city_digital_twin/
├── README.md                          ← top-level pointer to the real docs
├── Unity_fundamental/                 ← unrelated Unity tutorial project (ignore for the digital twin)
└── smart_city_digital_twin/
    ├── README.md                      ← the authoritative setup/run guide (very detailed)
    ├── 2D_simulation/
    │   ├── Christchurch_Central_City_main_streets.sumocfg   ← main SUMO config (used by 2D and 3D)
    │   ├── requirements.txt           ← Python deps for the data pipeline
    │   ├── README.md
    │   ├── data/
    │   │   ├── input/                 ← raw OpenData CSVs, Miovision traffic-count workbooks
    │   │   └── output/
    │   │       ├── network/           ← generated .net.xml, .add.xml, OSM extracts
    │   │       └── demand/            ← generated route/trip .xml, traffic CSVs
    │   └── scripts/                   ← Python pipeline: parsing, network/demand generation, calibration, Leaflet map
    └── 3D_simulation/                 ← Unity project
        ├── Assets/
        │   ├── SumoVehicleSpawner.cs          ← connects to TraCI, spawns/moves vehicles each SUMO step
        │   ├── ChristchurchCalibration.cs     ← maps SUMO coords → real-world lat/lon → Unity world position
        │   ├── ChristchurchIntersectionsGizmo.cs
        │   ├── SimpleFlyCamera.cs             ← free-fly camera for exploring the 3D scene
        │   ├── TraCIHandshake.cs
        │   ├── TraciLibrary/                  ← third-party TraCI protocol client for C#
        │   ├── StreamingAssets/Christchurch/calibration.json  ← generated coordinate-alignment data
        │   ├── Christchurch_Central_City_3D.fbx  ← 3D city mesh
        │   └── Scenes/SampleScene.unity       ← the scene to open and Play
        ├── Packages/manifest.json
        └── ProjectSettings/           ← Unity editor version = 6000.3.11f1
```

## 4. Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| **Eclipse SUMO** | 1.20+ (1.26 tested) | Runs the traffic simulation (`sumo`, `sumo-gui`, `netconvert` must be on `PATH`) |
| **Python** | 3.10+ | Only needed for the data pipeline / calibration scripts |
| **Unity Hub + Unity Editor** | 6000.3.11f1 (Unity 6) — matches `ProjectSettings/ProjectVersion.txt` | Only needed for the 3D digital twin |
| **Git** | any recent version | Cloning/managing the repo |
| OS | macOS or Windows | SUMO can run in a Windows VM while Unity runs on the host Mac, if needed |

Download SUMO from https://sumo.dlr.de/docs/Downloads.php (verify the exact download steps there — this repo doesn't bundle an installer). Download Unity Hub from https://unity.com/download and use it to install exactly Unity `6000.3.11f1` (or close enough — check `smart_city_digital_twin/3D_simulation/ProjectSettings/ProjectVersion.txt` for the exact version this project was authored in).

You do **not** need Unity or Python to just run the 2D SUMO simulation.

## 5. Installation

Clone the repo, then set up whichever piece you need.

```bash
git clone <this-repo-url>
cd demo_smart_city_digital_twin/smart_city_digital_twin
```

### 5a. Python data pipeline (optional — only for regenerating data/calibration)

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r 2D_simulation/requirements.txt
# optional, for calibration scripts:
pip install numpy ufbx
```

### 5b. SUMO

Install SUMO for your OS and confirm the binaries are on `PATH`:

```bash
sumo --version
sumo-gui --version
netconvert --version
```

If these fail, see [Troubleshooting](#11-troubleshooting).

### 5c. Unity (only for the 3D twin)

Install Unity Hub, add Unity Editor `6000.3.11f1` via Hub, then use **Hub → Open → select `smart_city_digital_twin/3D_simulation/`**. Let Unity import assets on first open (can take several minutes).

## 6. Configuration

There's no `.env` file or secrets in this project — configuration lives in plain files:

- **`2D_simulation/Christchurch_Central_City_main_streets.sumocfg`** — the SUMO config: which network file, route file, and additional-file to load, plus simulation time window (`begin=23400` = 06:30, `end=86400` = 24:00) and `step-length=1` (1 second per sim step). Both the 2D-only and 2D+3D runs use this same file.
- **`Assets/StreamingAssets/Christchurch/calibration.json`** — generated by `calibrate_christchurch.py`; tells Unity how to convert SUMO's local (x,y) coordinates into real-world NZTM/WGS84 coordinates and then into Unity world-space on the FBX map. You normally don't hand-edit this — regenerate it if vehicles look offset from the roads.
- **Unity Inspector fields on `SumoVehicleSpawner`** (attached to a GameObject in `SampleScene.unity`) — this is where you set `serverIP`, `serverPort` (8813), and `stepLengthSeconds` to match the `.sumocfg`. These are effectively the "runtime config" for the 3D side.

There are no environment variables required by this project.

## 7. Running the Project

### 7a. 2D SUMO only

```bash
cd smart_city_digital_twin/2D_simulation
sumo-gui -c Christchurch_Central_City_main_streets.sumocfg
```
Click **Run** (▶) in the SUMO-GUI toolbar to start traffic flowing.

Headless (no GUI, e.g. for scripted runs):
```bash
sumo -c Christchurch_Central_City_main_streets.sumocfg
```

### 7b. 3D Unity digital twin (SUMO + Unity together)

**Start order matters: SUMO first, then Unity Play.**

Terminal 1:
```bash
cd smart_city_digital_twin/2D_simulation
sumo-gui -c Christchurch_Central_City_main_streets.sumocfg --remote-port 8813 --start
```
Leave this running — `--remote-port 8813` opens the TraCI socket Unity connects to; `--start` begins stepping immediately.

Unity:
1. Open `3D_simulation/` in Unity Hub, open `Assets/Scenes/SampleScene.unity`.
2. Select the GameObject holding `SumoVehicleSpawner` and confirm: Server IP `127.0.0.1`, Server Port `8813`, Step Length Seconds `1` (must match the `.sumocfg`'s `step-length`), "Apply Christchurch Calibration On Start" checked.
3. Press **Play**. Yellow cubes = cars, teal cubes = buses. Use `SimpleFlyCamera` (WASD + mouse, check the script for exact bindings) to look around.

### 7c. Leaflet intersection map (optional, standalone)

```bash
cd smart_city_digital_twin
python3 -m http.server 8765
```
Open `http://localhost:8765/2D_simulation/scripts/intersection_map.html` in a browser.

## 8. How the Code Works

**Data flow, high level:**

```
Raw data (data/input/) 
   → Python scripts (2D_simulation/scripts/) 
   → SUMO network + demand files (data/output/network, data/output/demand) 
   → SUMO engine reads them via .sumocfg 
   → [3D path only] TraCI socket (port 8813) 
   → Unity SumoVehicleSpawner.cs polls vehicle positions every step 
   → ChristchurchCalibration.cs converts SUMO (x,y) → lat/lon → Unity world position 
   → cubes/prefabs rendered on the FBX city map
```

- **`Christchurch_Central_City_main_streets.sumocfg`** is the single source of truth for which network (`.net.xml`) and routes (`.rou.xml`) SUMO loads — both the 2D-only and 3D runs point at the same file, so they always show identical traffic.
- **`SumoVehicleSpawner.cs`** (`Start()`/`Update()`-style Unity MonoBehaviour) opens a `Socket` to SUMO's TraCI port, uses `TraciLibrary/` (a bundled C# TraCI client) to issue simulation-step and vehicle-position commands each frame/step, then spawns or moves a `GameObject` (cube or `vehiclePrefab`) per vehicle ID reported by SUMO. Buses are distinguished by SUMO `vType` id (`busTypeIds`) and get a different color/scale.
- **`ChristchurchCalibration.cs`** loads `calibration.json` at `Start()` and exposes static conversion helpers (SUMO plane → NZTM → WGS84 → Unity world space) so vehicle cubes land on the correct road in the 3D mesh, not just at raw SUMO simulation coordinates.
- **The Python pipeline** (`2D_simulation/scripts/`) is organized around `sim_pipeline.py` (a large shared module with pipeline "steps") and thin entry-point scripts (`create_network.py`, `create_demand.py`) that call into it. `traffic_counts_parser.py` reads Miovision Excel workbooks into CSV; `match_intersection_opendata.py` geocodes intersections; `sumo_network_from_geo.py` / `sumo_demand_from_traffic_csv.py` build an alternate, simplified 96-intersection SUMO network from that data (separate from the main OSM-based network used by the `.sumocfg`).

## 9. Step-by-Step Walkthrough (first-time run)

1. **Install SUMO**, verify `sumo-gui --version` works.
2. **Run 2D only first** — simplest path to confirm the environment is sane:
   ```bash
   cd smart_city_digital_twin/2D_simulation
   sumo-gui -c Christchurch_Central_City_main_streets.sumocfg
   ```
   Press Run; you should see traffic on Christchurch's central-city streets between 06:30–24:00 sim time.
3. **If that works**, install Unity 6000.3.11f1 and open `3D_simulation/` via Unity Hub. Let it import (this can be slow the first time).
4. **Re-launch SUMO with TraCI enabled**: `sumo-gui -c Christchurch_Central_City_main_streets.sumocfg --remote-port 8813 --start`.
5. **Open `SampleScene.unity`** in Unity, check the `SumoVehicleSpawner` fields match (`127.0.0.1:8813`, step length `1`), press **Play**.
6. **Watch cubes appear** on the 3D map as vehicles enter the simulation — this confirms the TraCI bridge is working end-to-end.
7. *(Optional)* Explore the Leaflet map (§7c) to see the underlying 96-intersection geo dataset independent of SUMO.

## 10. Example Modification

A safe, self-contained first change: **make vehicle cubes red instead of yellow, and make buses bigger.**

1. In Unity, select the GameObject with the `SumoVehicleSpawner` component (or edit defaults directly in `smart_city_digital_twin/3D_simulation/Assets/SumoVehicleSpawner.cs`).
2. In the Inspector under "Vehicle cubes (fallback)", change `Cube Color` from yellow to red — or edit the field default in code:
   ```csharp
   public Color cubeColor = Color.red; // was Color.yellow
   ```
3. Under "Bus cubes", bump `busScale` (`Vector3(2.5f, 3.4f, 12f)`) up, e.g. `new Vector3(3f, 4f, 14f)`.
4. Save, press Play again (with SUMO already running per §7b) — new vehicles should now spawn red, buses larger.

This is low-risk because it only touches cosmetic Inspector-exposed fields, not the TraCI connection logic or coordinate calibration.

For a pipeline-side change, e.g. widening the simulated time window: edit `2D_simulation/Christchurch_Central_City_main_streets.sumocfg`'s `<time>` block (`begin`/`end` are in seconds since midnight) and re-run `sumo-gui`.

## 11. Troubleshooting

| Problem | Likely cause | Fix |
|---|---|---|
| `sumo: command not found` / `netconvert: command not found` | SUMO not installed or not on `PATH` | Install SUMO, add `SUMO_HOME/bin` to `PATH` |
| SUMO fails to load the config | Missing `data/output/demand/traffic_trips.routed.rou.xml`, or wrong working directory | Run the `sumo-gui`/`sumo` command **from inside `2D_simulation/`**; confirm the file exists |
| Unity: "Could not connect to SUMO" | SUMO not started yet, or wrong IP/port | Start SUMO with `--remote-port 8813` **before** pressing Play in Unity |
| Unity: "peer shutdown" | A second TraCI client connected, or SUMO restarted mid-session | Restart SUMO; keep only one Unity Play session connected at a time |
| No vehicles appear in SUMO-GUI or Unity | Sim clock hasn't reached first trip departure, or Run wasn't pressed | Press **Run** in SUMO-GUI; check departure times in `traffic_trips.routed.rou.xml` |
| Vehicles floating off-road in Unity | Stale/mismatched `calibration.json` after a network or FBX change | Re-run `python3 2D_simulation/scripts/calibrate_christchurch.py --update-scene`, re-assign `Map Root` in the Inspector |
| `pip install` fails on `openpyxl`/`pyproj` | Wrong/missing Python version or venv not activated | Confirm `python3 --version` ≥ 3.10 and the venv is active (`source .venv/bin/activate`) |
| Unity project won't open / version mismatch warning | Installed Unity Editor version differs from `ProjectVersion.txt` (`6000.3.11f1`) | Install the matching version via Unity Hub, or let Unity offer to auto-upgrade (may cause asset changes) |
| SUMO and Unity on separate machines can't connect | Firewall blocking TCP 8813, or wrong VM IP | Get the VM's IPv4 via `ipconfig`, allow inbound TCP 8813 in Windows Firewall, set that IP as `serverIP` in Unity |

## 12. Next Steps

- Read [`smart_city_digital_twin/README.md`](smart_city_digital_twin/README.md) — it's the authoritative, already very complete reference this tutorial is built on, including the full script reference table (§7) and data sources (§10).
- Explore `2D_simulation/scripts/sim_pipeline.py` if you want to understand or extend the data pipeline — it's the largest file in the repo (~312 KB) and centralizes most pipeline logic.
- If you want to regenerate the network/demand from scratch rather than using the checked-in `data/output/` files, see `2D_simulation/README.md`'s "Build pipeline" section (`create_network.py`, `create_demand.py`).
- No license file or CI/test setup was found in this repo — if you plan to distribute or automate testing, verify that's actually absent before assuming so, and add one as needed.
