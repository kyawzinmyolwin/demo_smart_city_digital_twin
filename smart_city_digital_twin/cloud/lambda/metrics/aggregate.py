"""
Per-tick traffic-metrics aggregation for the Christchurch CBD digital twin.

This module is deliberately AWS-free and SUMO-free: it takes a vehicle snapshot
dict (the exact schema produced by the Phase 1 emitter, see
``2D_simulation/scripts/emitter.py``) and returns an aggregated metrics dict.
Keeping it pure means it is unit-tested with plain dicts and no cloud stack (see
tests/test_aggregate.py) — the same design split the emitter uses between
``serialize_vehicles`` and the WebSocket transport.

The Lambda handler in ``handlers.py`` is the only thing that touches AWS; it
calls ``aggregate_snapshot`` and forwards the result.

Metrics produced (all derived from a single instantaneous snapshot):

- ``vehicleCount``    : number of vehicles on the network this tick.
- ``avgSpeedMps`` /
  ``avgSpeedKmh``     : mean speed over all vehicles (0 when the network is empty).
- ``stoppedCount`` /
  ``movingCount``     : split at ``stopped_speed_mps`` (queue/gridlock indicator).
- ``congestionIndex`` : 1 - avgSpeed/freeFlow, clamped to [0, 1]. 0 = free-flowing
                        at (or above) the free-flow speed, 1 = fully stopped.
- ``flowIndex``       : vehicleCount * avgSpeedKmh, a *relative* throughput proxy
                        from the fundamental relation q = k*v (density x speed).
                        It is an indicator for trend/scenario comparison, not an
                        absolute veh/h count — true flow needs cross-section
                        counting, which a single snapshot cannot provide.
"""
from __future__ import annotations

from typing import Any

# NZ urban default speed limit, 50 km/h -> m/s. Used as the free-flow reference
# for the congestion index. Configurable per call so a scenario with a different
# posted limit can override it.
DEFAULT_FREE_FLOW_MPS = 50.0 / 3.6

# A vehicle at or below this speed is treated as stopped (queued at a light,
# gridlocked). 0.5 m/s ~= 1.8 km/h: slow enough to exclude normal crawling.
DEFAULT_STOPPED_SPEED_MPS = 0.5


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def aggregate_snapshot(
    snapshot: dict[str, Any],
    *,
    free_flow_mps: float = DEFAULT_FREE_FLOW_MPS,
    stopped_speed_mps: float = DEFAULT_STOPPED_SPEED_MPS,
) -> dict[str, Any]:
    """Reduce one vehicle snapshot to a per-tick metrics dict.

    Parameters
    ----------
    snapshot:
        A dict matching the emitter schema: ``simId``, ``simTime``,
        ``vehicleCount``, and a ``vehicles`` list of ``{speed, ...}`` entries.
        Missing ``vehicles`` is treated as an empty network.
    free_flow_mps:
        Speed (m/s) treated as uncongested for the congestion index.
    stopped_speed_mps:
        Threshold (m/s) below which a vehicle counts as stopped.

    Returns
    -------
    dict with the metrics described in the module docstring, plus the passthrough
    identifiers (``tick``, ``simId``, ``simTime``) so downstream consumers can
    line metrics up with the originating snapshot.
    """
    if free_flow_mps <= 0:
        raise ValueError("free_flow_mps must be positive")

    vehicles = snapshot.get("vehicles") or []
    speeds = [float(v["speed"]) for v in vehicles]
    count = len(speeds)

    if count:
        avg_speed_mps = sum(speeds) / count
        stopped = sum(1 for s in speeds if s <= stopped_speed_mps)
    else:
        avg_speed_mps = 0.0
        stopped = 0

    avg_speed_kmh = avg_speed_mps * 3.6
    congestion_index = _clamp(1.0 - avg_speed_mps / free_flow_mps, 0.0, 1.0)
    flow_index = count * avg_speed_kmh

    return {
        "tick": snapshot.get("tick"),
        "simId": snapshot.get("simId"),
        "simTime": snapshot.get("simTime"),
        "vehicleCount": count,
        "avgSpeedMps": round(avg_speed_mps, 3),
        "avgSpeedKmh": round(avg_speed_kmh, 3),
        "stoppedCount": stopped,
        "movingCount": count - stopped,
        "congestionIndex": round(congestion_index, 4),
        "flowIndex": round(flow_index, 1),
    }
