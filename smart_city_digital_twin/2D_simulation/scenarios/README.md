# Test scenarios

Small, self-contained SUMO scenarios for exercising the emitter → dashboard →
cloud pipeline without the full ~92,000-vehicle demand.

## low_traffic — 8 vehicles

`low_traffic.sumocfg` + `low_traffic.rou.xml`: the same real Christchurch network,
but only the first 8 vehicles from `data/output/demand/traffic_trips.routed.rou.xml`
(all depart 06:30 / sim time 23400). Their routes are copied verbatim from the
routed demand, so they are valid on the network by construction.

Regenerate with a different count by re-running the extractor (change `N`):

```python
import xml.etree.ElementTree as ET
N = 8
src = "data/output/demand/traffic_trips.routed.rou.xml"
out = ['<?xml version="1.0" encoding="UTF-8"?>', '<routes>',
       '    <vType id="car" vClass="passenger" />',
       '    <vType id="bus" vClass="bus" color="0,122,135" />']
n = 0
for _, el in ET.iterparse(src, events=("end",)):
    if el.tag == "vehicle":
        out.append("    " + ET.tostring(el, encoding="unicode").strip())
        n += 1
        if n >= N:
            break
        el.clear()
out.append("</routes>")
open("scenarios/low_traffic.rou.xml", "w").write("\n".join(out) + "\n")
```

### Run it (from `2D_simulation/`)

One command via the `--sumocfg` override on `run_traci.py`:

```bash
python scripts/run_traci.py --sumocfg scenarios/low_traffic.sumocfg --no-gui --emit
```

Or attach to a SUMO you launch yourself (no `--sumocfg` needed):

```bash
sumo -c scenarios/low_traffic.sumocfg --remote-port 8813 --step-length 1 --start &
python scripts/run_traci.py --connect --emit
```

The 8 vehicles appear at the 06:30 jump and run until their routes finish, so the
sim goes idle and the loop stops on its own — a short, deterministic run.
