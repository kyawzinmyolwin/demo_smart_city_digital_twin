# Test-scenario support — implementation notes

Engineering record for the low-traffic test scenarios and the `run_traci.py`
flags that drive them. The user-facing "how to run it" lives in `README.md`;
this file documents *what changed, why, and how it was verified*.

Branch: `claude/next-step-nun1nw` · Commits: `2bbf6cc`, `f3edd00`.

---

## Motivation

The real demand is ~92,000 vehicles — too heavy for quickly eyeballing the
emitter/dashboard/cloud pipeline. We wanted a small, reproducible run. A first
8-vehicle scenario worked but was **not watchable**, for two independent reasons
(both inherent, not bugs):

1. **The run drains fast.** `run_traci.py`'s `_should_stop()` ends the loop once
   `traci.simulation.getMinExpectedNumber() <= 0`. Eight vehicles all departing at
   06:30 finish their routes within ~1–2 min of *sim* time, so the network empties
   and the loop exits.
2. **No real-time pacing.** The emit loop (`_run_emitting`) steps flat out
   (`await asyncio.sleep(0)`). With almost no vehicles there is almost no per-step
   computation, so minutes of sim time elapse in ~1 second of wall-clock. (The full
   92k run only *felt* watchable because its heavy per-step cost paced it.)

The fix addresses both: a **flow-based scenario** keeps a few vehicles present for
several minutes of sim time, and a **`--real-time`** flag paces playback to the
wall clock.

---

## Changes by file

### `scripts/run_traci.py` (additive; default behaviour unchanged)

**1. New CLI flags** (in `build_parser()`):

| Flag | Type / default | Effect |
|------|----------------|--------|
| `--sumocfg PATH` | str / `None` | Launch an alternate SUMO config instead of the project default `SUMOCFG`. Launch mode only — ignored with `--connect`. |
| `--real-time` | flag / off | Pace the emitting loop to wall-clock time so a light scenario is watchable. Emit mode only. |
| `--speed X` | float / `1.0` | Playback multiplier for `--real-time` (`2` = twice real time, `0.5` = half). |

**2. Config selection** (in `main()`): the launch command now uses
`str(args.sumocfg) if args.sumocfg else str(SUMOCFG)`. When `--sumocfg` is absent
the original `SUMOCFG` is used, so existing invocations are unaffected.

**3. Real-time pacing** (in `_run_emitting()`): before the loop it anchors
`sim_start = traci.simulation.getTime()` and `wall_start = time.monotonic()`. Each
iteration, when `--real-time` is set, it computes how far ahead of the wall clock
the sim is and sleeps the difference:

```python
lag = 0.0
if args.real_time:
    sim_elapsed = traci.simulation.getTime() - sim_start
    lag = (sim_elapsed / speed) - (time.monotonic() - wall_start)
await asyncio.sleep(lag if lag > 0 else 0)
```

Anchoring to *elapsed sim time* (rather than sleeping a fixed amount per step)
keeps playback accurate regardless of step count or step length, and self-corrects
if a step runs long. When `--real-time` is off, `lag` stays `0` and the call
degrades to the original `await asyncio.sleep(0)` — an event-loop yield only.

### `scenarios/low_traffic.{sumocfg,rou.xml}` — deterministic 8-vehicle run

The first 8 `<vehicle>` entries from `data/output/demand/traffic_trips.routed.rou.xml`
(all depart 06:30), routes copied verbatim so they are valid on the real network by
construction. Short window (23400–24000). Best as a **quick/CI check** — it
finishes in ~a second of wall-clock.

### `scenarios/low_traffic_flow.{sumocfg,rou.xml}` — watchable steady trickle

Three `<flow>`s inject ~4–6 vehicles at a time along 3 real routes (reused from the
8-vehicle file) for 6 min of sim time (23400–23760). The network stays populated,
so paired with `--real-time` the dashboard shows continuous movement for ~6 min.

### `scenarios/README.md`

User-facing usage for both scenarios, the run commands, and how to regenerate the
route files with a different vehicle count.

---

## Usage

```bash
# From 2D_simulation/

# Quick deterministic check (finishes in ~1 s):
python scripts/run_traci.py --sumocfg scenarios/low_traffic.sumocfg --no-gui --emit

# Watchable ~6-minute live run (a few vehicles throughout):
python scripts/run_traci.py --sumocfg scenarios/low_traffic_flow.sumocfg \
    --no-gui --emit --real-time            # --speed 2 for ~3 min; Ctrl-C to stop

# Attach to a SUMO you launched yourself (no --sumocfg needed):
sumo -c scenarios/low_traffic_flow.sumocfg --remote-port 8813 --step-length 1 --start &
python scripts/run_traci.py --connect --emit --real-time
```

Point `intersection_map.html` at `ws://localhost:8765` to see the vehicles.

---

## Design decisions

- **Additive, backward-compatible.** Three new optional flags; all default to the
  prior behaviour. The original stepping/emit path is unchanged when they're unset,
  consistent with how `--emit` was originally added alongside (not in place of) the
  sync loop.
- **Real routes, not synthesised.** Both scenarios reuse edge lists lifted from the
  already-routed demand, so every route is guaranteed valid on this network — no
  routing step, no invalid-edge failures.
- **Flows for persistence.** One-shot vehicles drain; `<flow>` with a period keeps a
  bounded few vehicles present across the whole window without ever becoming a flood.
- **Pace anchored to sim time.** Robust to variable step cost and `--speed`, unlike a
  fixed per-step delay or relying on `sumo-gui --delay` (which does not throttle a
  TraCI-driven loop).

---

## Verification

Checked in this environment (SUMO is **not** installed here, so no live run):

- `run_traci.py` compiles (`python -m py_compile`).
- All four scenario files are well-formed XML (this caught and fixed an invalid
  `--` sequence inside an XML comment in the flow files).
- The `--sumocfg` / `--real-time` / `--speed` flags are present and wired.
- The `../data/...` net and additional-file paths resolve from `scenarios/`.

**Still to confirm on a machine with SUMO** (e.g. the Vagrant VM, from a venv with
`pyproj` + `websockets`): a real `--real-time` run of the flow scenario streams for
~6 minutes with a few vehicles visible on the dashboard throughout.
