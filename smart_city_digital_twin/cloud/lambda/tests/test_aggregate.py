"""
Unit tests for metrics.aggregate — no AWS, no SUMO, no network.

Mirrors the emitter's test approach: feed the pure function plain snapshot dicts
(the emitter's own output schema) and assert the aggregated metrics.

Run from cloud/lambda/:  python -m pytest tests/test_aggregate.py
Or without pytest:       python tests/test_aggregate.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "metrics"))

from aggregate import (  # noqa: E402
    DEFAULT_FREE_FLOW_MPS,
    aggregate_snapshot,
)


def _snapshot(speeds, sim_id="test-sim", sim_time=23460.1):
    """Build an emitter-shaped snapshot from a list of speeds (m/s)."""
    return {
        "tick": 1720123456789,
        "simId": sim_id,
        "simTime": sim_time,
        "vehicleCount": len(speeds),
        "vehicles": [
            {"id": "veh_%03d" % i, "lat": -43.5, "lng": 172.6, "speed": s,
             "lane": "edge_0_0", "accel": 0.0}
            for i, s in enumerate(speeds)
        ],
    }


def test_passthrough_identifiers():
    m = aggregate_snapshot(_snapshot([10.0]))
    assert m["tick"] == 1720123456789
    assert m["simId"] == "test-sim"
    assert m["simTime"] == 23460.1


def test_empty_network_is_zeroed_not_divide_by_zero():
    m = aggregate_snapshot(_snapshot([]))
    assert m["vehicleCount"] == 0
    assert m["avgSpeedMps"] == 0.0
    assert m["avgSpeedKmh"] == 0.0
    assert m["movingCount"] == 0
    assert m["stoppedCount"] == 0
    assert m["flowIndex"] == 0.0
    # Empty network reads as fully congested (avg speed 0). Documented behaviour.
    assert m["congestionIndex"] == 1.0


def test_missing_vehicles_key_treated_as_empty():
    m = aggregate_snapshot({"simId": "s", "simTime": 1.0})
    assert m["vehicleCount"] == 0
    assert m["avgSpeedMps"] == 0.0


def test_free_flow_is_uncongested():
    # Everyone at exactly the free-flow speed -> congestion index 0.
    m = aggregate_snapshot(_snapshot([DEFAULT_FREE_FLOW_MPS] * 3))
    assert m["vehicleCount"] == 3
    assert m["congestionIndex"] == 0.0
    assert m["stoppedCount"] == 0
    assert m["movingCount"] == 3


def test_above_free_flow_clamps_at_zero():
    m = aggregate_snapshot(_snapshot([DEFAULT_FREE_FLOW_MPS * 2]))
    assert m["congestionIndex"] == 0.0


def test_all_stopped_is_fully_congested():
    m = aggregate_snapshot(_snapshot([0.0, 0.0, 0.0, 0.0]))
    assert m["avgSpeedMps"] == 0.0
    assert m["congestionIndex"] == 1.0
    assert m["stoppedCount"] == 4
    assert m["movingCount"] == 0
    assert m["flowIndex"] == 0.0


def test_stopped_threshold_split():
    # 0.4 m/s is below the 0.5 default threshold; 0.6 is above it.
    m = aggregate_snapshot(_snapshot([0.4, 0.6, 10.0]))
    assert m["stoppedCount"] == 1
    assert m["movingCount"] == 2


def test_known_average_and_flow_index():
    # Speeds 10 and 20 m/s -> avg 15 m/s = 54 km/h, 2 vehicles.
    m = aggregate_snapshot(_snapshot([10.0, 20.0]))
    assert m["avgSpeedMps"] == 15.0
    assert m["avgSpeedKmh"] == 54.0
    # flowIndex = count * avgSpeedKmh = 2 * 54 = 108.0
    assert m["flowIndex"] == 108.0
    # congestion = 1 - 15/(50/3.6) = 1 - 15/13.888.. -> clamped to 0 (15 > free flow)
    assert m["congestionIndex"] == 0.0


def test_partial_congestion_value():
    # avg 6.944 m/s = half the free-flow speed -> congestion index 0.5.
    half = DEFAULT_FREE_FLOW_MPS / 2
    m = aggregate_snapshot(_snapshot([half, half]))
    assert m["congestionIndex"] == 0.5


def test_custom_free_flow_override():
    # With a 100 km/h free-flow reference, 50 km/h reads as 0.5 congestion.
    speeds = [50.0 / 3.6, 50.0 / 3.6]
    m = aggregate_snapshot(_snapshot(speeds), free_flow_mps=100.0 / 3.6)
    assert m["congestionIndex"] == 0.5


def test_nonpositive_free_flow_rejected():
    try:
        aggregate_snapshot(_snapshot([1.0]), free_flow_mps=0.0)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for non-positive free_flow_mps")


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS %s" % name)
            except AssertionError as exc:
                failures += 1
                print("FAIL %s: %s" % (name, exc))
    raise SystemExit(1 if failures else 0)
