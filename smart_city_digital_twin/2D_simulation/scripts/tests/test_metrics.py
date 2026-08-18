"""
Unit tests for metrics.compute_tick_metrics — pure, no InfluxDB/SUMO required.

Run:  python tests/test_metrics.py    (or: python -m pytest tests/test_metrics.py)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from metrics import compute_tick_metrics  # noqa: E402


def _snap(speeds, sim_time=100.0, sim_id="s"):
    return {
        "simId": sim_id,
        "simTime": sim_time,
        "vehicles": [{"id": f"v{i}", "speed": s} for i, s in enumerate(speeds)],
    }


def test_basic_aggregation():
    # speeds: 0 (stopped), 2 (slow), 5 (amber), 10 (free) -> 2 below 3 m/s
    m = compute_tick_metrics(_snap([0.0, 2.0, 5.0, 10.0]))
    assert m["vehicleCount"] == 4
    assert m["avgSpeed"] == 4.25            # (0+2+5+10)/4
    assert m["stoppedCount"] == 2           # 0 and 2 are < 3
    assert m["movingCount"] == 2
    assert m["congestionIndex"] == 0.5      # 2/4
    assert m["simTime"] == 100.0
    assert m["simId"] == "s"


def test_empty_network():
    m = compute_tick_metrics(_snap([]))
    assert m["vehicleCount"] == 0
    assert m["avgSpeed"] == 0.0
    assert m["congestionIndex"] == 0.0
    assert m["stoppedCount"] == 0
    assert m["movingCount"] == 0


def test_all_congested():
    m = compute_tick_metrics(_snap([0.0, 0.5, 1.0]))
    assert m["congestionIndex"] == 1.0
    assert m["movingCount"] == 0


def test_custom_threshold():
    # With slow_speed=6, the 5 m/s vehicle also counts as congested.
    m = compute_tick_metrics(_snap([5.0, 10.0]), slow_speed=6.0)
    assert m["stoppedCount"] == 1
    assert m["congestionIndex"] == 0.5


def test_ignores_bad_speeds():
    # None / non-numeric speeds are skipped for the average, not crashed on.
    snap = {"simId": "s", "simTime": 1.0, "vehicles": [
        {"id": "a", "speed": 4.0},
        {"id": "b", "speed": None},
        {"id": "c"},  # no speed key
    ]}
    m = compute_tick_metrics(snap)
    assert m["vehicleCount"] == 3           # count is all vehicles
    assert m["avgSpeed"] == 4.0             # average over valid speeds only
    assert m["movingCount"] == 1


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
