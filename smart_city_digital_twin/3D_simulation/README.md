# 3D simulation — Unity digital twin

Same SUMO config as 2D, plus TraCI for Unity vehicle sync.

**Full instructions:** [`../README.md`](../README.md) (§5)

## Quick start

**Terminal 1 — SUMO** (from `smart_city_digital_twin/2D_simulation/`):

```bash
sumo-gui -c Christchurch_Central_City_main_streets.sumocfg --remote-port 8813 --start
```

**Terminal 2 — Unity:**

1. Open `3D_simulation/` in Unity Hub.  
2. Play with `SumoVehicleSpawner` (`serverIP=127.0.0.1`, `serverPort=8813`, `stepLengthSeconds=1`).
