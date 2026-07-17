"""
Live vehicle-state emitter for the Christchurch CBD SUMO simulation.

Two responsibilities, deliberately kept apart:

1. ``serialize_vehicles`` — pure function. Given a live ``traci`` connection and
   a ``sumolib`` net (only used for XY -> WGS84 conversion), it returns the JSON
   snapshot dict. It imports nothing from SUMO, so it can be unit-tested with
   fakes and no SUMO install (see tests/test_emitter.py).

2. ``Broadcaster`` + ``serve`` — the async WebSocket side. The broadcaster keeps
   the set of connected browsers and the latest snapshot, so a brand-new client
   gets the current state immediately instead of waiting for the next tick.

run_traci.py owns the TraCI stepping loop and calls into here. This module never
touches traci itself except through the object handed to ``serialize_vehicles``.
"""
from __future__ import annotations

import json
import time
from typing import Any, Iterable

# websockets is only needed for the live server, not for serialization, so the
# import is deferred into serve()/Broadcaster usage. That keeps this module (and
# the unit test) importable without the dependency installed.


def serialize_vehicles(traci: Any, net: Any, sim_id: str) -> dict[str, Any]:
    """Build one JSON snapshot of every vehicle currently on the network.

    Parameters
    ----------
    traci:
        A live TraCI connection (or a fake exposing the same attributes).
    net:
        A sumolib net with ``convertXY2LonLat(x, y)`` -> ``(lon, lat)``. Passed
        in rather than imported so this function stays SUMO-free and testable.
    sim_id:
        Scenario identifier echoed back to clients.

    Returns
    -------
    dict matching the schema documented in CLAUDE.md.
    """
    vehicle_ids = traci.vehicle.getIDList()
    vehicles: list[dict[str, Any]] = []
    for vid in vehicle_ids:
        # SUMO works in projected metres (x east, y north). The browser map
        # (Leaflet) wants WGS84 lon/lat, so convert per vehicle.
        x, y = traci.vehicle.getPosition(vid)
        lon, lat = net.convertXY2LonLat(x, y)
        vehicles.append(
            {
                "id": vid,
                "lat": round(lat, 6),
                "lng": round(lon, 6),
                "speed": round(traci.vehicle.getSpeed(vid), 3),
                "lane": traci.vehicle.getLaneID(vid),
                "accel": round(traci.vehicle.getAcceleration(vid), 3),
            }
        )

    return {
        "tick": int(time.time() * 1000),          # wall-clock ms, for the client
        "simId": sim_id,
        "simTime": round(traci.simulation.getTime(), 3),
        "vehicleCount": len(vehicles),
        "vehicles": vehicles,
    }


def to_json(snapshot: dict[str, Any]) -> str:
    """Serialise a snapshot to a compact JSON string for the wire."""
    return json.dumps(snapshot, separators=(",", ":"))


class Broadcaster:
    """Tracks connected WebSocket clients and the most recent snapshot.

    The stepping loop calls :meth:`broadcast` each tick. New clients that connect
    between ticks are handed :attr:`latest` on connect so the map is never blank.
    """

    def __init__(self) -> None:
        self._clients: set[Any] = set()
        self.latest: str | None = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    def register(self, ws: Any) -> None:
        self._clients.add(ws)

    def unregister(self, ws: Any) -> None:
        self._clients.discard(ws)

    async def broadcast(self, message: str) -> None:
        """Send ``message`` to every connected client; drop ones that error."""
        self.latest = message
        if not self._clients:
            return
        dead: list[Any] = []
        for ws in self._clients:
            try:
                await ws.send(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.unregister(ws)


async def serve(broadcaster: Broadcaster, host: str, port: int):
    """Start the WebSocket server and return the running server object.

    Each connection: send the current snapshot right away, then just hold the
    socket open (we only push; clients don't send anything the emitter reads).
    """
    import websockets

    async def handler(ws: Any) -> None:
        broadcaster.register(ws)
        try:
            if broadcaster.latest is not None:
                await ws.send(broadcaster.latest)
            await ws.wait_closed()
        finally:
            broadcaster.unregister(ws)

    return await websockets.serve(handler, host, port)
