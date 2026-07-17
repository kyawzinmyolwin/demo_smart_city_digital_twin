"""
Run the Christchurch Central City simulation under TraCI control.

Demand in data/output/demand/traffic_trips.routed.rou.xml starts at 06:30 (sim time 23400 s).

Usage:
  # Launch sumo-gui and jump to morning traffic:
  python scripts/run_traci.py --jump-to 23400

  # Connect to sumo-gui you already started with --remote-port:
  sumo-gui -c Christchurch_Central_City_main_streets.sumocfg ^
      --remote-port 8813 --step-length 0.1 --start
  python run_traci.py --connect --jump-to 23400

  # Step in smaller chunks if a large jump crashes SUMO:
  python scripts/run_traci.py --jump-to 23400 --chunk 600
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import time
from pathlib import Path

from _sim_root import SIM_ROOT  # noqa: E402
from emitter import Broadcaster, serialize_vehicles, serve, to_json
from sim_pipeline import SUMOCFG, setup_sumolib, sumo_bin

# Earliest vehicle depart in data/output/demand/traffic_trips.routed.rou.xml (06:30).
DEFAULT_JUMP_TO = 23400.0
DEFAULT_PORT = 8813
DEFAULT_EMIT_PORT = 8765
DEFAULT_SIM_ID = "christchurch-cbd-001"


def _ensure_sumo_tools() -> bool:
    """Make ``traci``/``sumolib`` importable across platforms.

    Tries the repo's Windows-oriented ``setup_sumolib`` first (unchanged). If that
    fails — as it does on macOS/Linux, where the finder looks for netconvert.exe —
    fall back to ``$SUMO_HOME/tools``, which is the correct layout for a Homebrew
    or Linux SUMO install. Purely additive: never changes the Windows path.
    """
    if setup_sumolib() is not None:
        return True
    home = os.environ.get("SUMO_HOME")
    if home:
        tools = Path(home) / "tools"
        if tools.is_dir():
            s = str(tools)
            if s not in sys.path:
                sys.path.insert(0, s)
            return True
    return False


def _import_traci():
    try:
        import traci  # type: ignore
    except ImportError as exc:
        raise SystemExit(
            "Could not import traci. Check SUMO_HOME / C:\\Sumo\\tools."
        ) from exc
    return traci


def step_to(traci, target: float, *, chunk: float) -> None:
    """Advance simulation to target time, optionally in chunks."""
    target = float(target)
    if chunk <= 0:
        traci.simulationStep(target)
        _print_status(traci)
        return

    while True:
        current = traci.simulation.getTime()
        if current >= target:
            break
        next_t = min(current + chunk, target)
        traci.simulationStep(next_t)
        _print_status(traci)


def _print_status(traci) -> None:
    t = traci.simulation.getTime()
    n = traci.simulation.getMinExpectedNumber()
    print(f"  sim time {t:8.1f}s ({_fmt_clock(t)}), vehicles on network: {n}")


def _fmt_clock(seconds: float) -> str:
    s = int(seconds) % 86400
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}"


def _should_stop(traci, args) -> bool:
    """Shared end-of-run test for both the sync and emitting loops."""
    t = traci.simulation.getTime()
    if args.end is not None and t >= args.end:
        return True
    return traci.simulation.getMinExpectedNumber() <= 0 and t >= (args.jump_to or 0)


def _load_net():
    """Load the sumolib net once, for XY -> WGS84 conversion in the emitter."""
    import sumolib  # type: ignore

    from sim_pipeline import NET_XML

    return sumolib.net.readNet(str(NET_XML))


async def _run_emitting(traci, args) -> None:
    """Step the sim and broadcast each Nth step's snapshot over WebSocket.

    This is the async twin of the plain while-loop in main(). The key line is the
    ``await asyncio.sleep(0)`` at the bottom: it hands control back to the event
    loop so the WebSocket server can accept connections and flush frames before
    we take the next (blocking) simulation step.
    """
    net = _load_net()
    broadcaster = Broadcaster()
    server = await serve(broadcaster, args.emit_host, args.emit_port)
    print(f"Emitter live on ws://{args.emit_host}:{args.emit_port} (sim id: {args.sim_id})")

    step = 0
    try:
        print("Running simulation ...")
        while not _should_stop(traci, args):
            t = traci.simulation.getTime()
            traci.simulationStep()
            step += 1
            # Only serialise when someone is listening — no clients, no work.
            if broadcaster.client_count and step % args.emit_interval == 0:
                snapshot = serialize_vehicles(traci, net, args.sim_id)
                await broadcaster.broadcast(to_json(snapshot))
            if int(t) % 60 == 0:
                _print_status(traci)
            await asyncio.sleep(0)  # yield to the WebSocket server
    finally:
        server.close()
        await server.wait_closed()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Control SUMO via TraCI for this project.")
    p.add_argument(
        "--connect",
        action="store_true",
        help="Connect to an already running sumo-gui (--remote-port), do not launch SUMO",
    )
    p.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"TraCI port (default: {DEFAULT_PORT})",
    )
    p.add_argument("--begin", type=float, default=0.0, help="Simulation begin time (launch mode)")
    p.add_argument(
        "--jump-to",
        type=float,
        default=DEFAULT_JUMP_TO,
        metavar="SEC",
        help=f"Advance to this sim time before the main loop (default: {int(DEFAULT_JUMP_TO)} = 06:30)",
    )
    p.add_argument(
        "--chunk",
        type=float,
        default=3600.0,
        metavar="SEC",
        help="Step in chunks of SEC when jumping (0 = one step; default: 3600)",
    )
    p.add_argument(
        "--step-length",
        type=float,
        default=0.1,
        help="SUMO step length in seconds (launch mode; default: 0.1)",
    )
    p.add_argument("--delay", type=int, default=100, help="sumo-gui delay ms (launch mode)")
    p.add_argument("--end", type=float, default=None, help="Stop at this sim time (default: run until idle)")
    p.add_argument("--gui", action="store_true", default=True, help="Use sumo-gui (default)")
    p.add_argument("--no-gui", action="store_false", dest="gui", help="Use headless sumo instead")
    # --- live emitter (Phase 1) ---
    p.add_argument(
        "--emit",
        action="store_true",
        help="Broadcast per-step vehicle state as JSON over WebSocket (see emitter.py)",
    )
    p.add_argument(
        "--emit-host",
        default="localhost",
        help="WebSocket bind host (default: localhost; use 0.0.0.0 to expose)",
    )
    p.add_argument(
        "--emit-port",
        type=int,
        default=DEFAULT_EMIT_PORT,
        help=f"WebSocket port (default: {DEFAULT_EMIT_PORT})",
    )
    p.add_argument(
        "--emit-interval",
        type=int,
        default=1,
        metavar="N",
        help="Emit every Nth simulation step (default: 1 = every step)",
    )
    p.add_argument(
        "--sim-id",
        default=DEFAULT_SIM_ID,
        help=f"Scenario id echoed to clients (default: {DEFAULT_SIM_ID})",
    )
    return p


def main() -> int:
    args = build_parser().parse_args()
    if not _ensure_sumo_tools():
        print(
            "Could not locate SUMO. Install it and set SUMO_HOME "
            "(macOS/Linux) or install to C:\\Sumo (Windows).",
            file=sys.stderr,
        )
        return 1

    traci = _import_traci()

    if args.connect:
        print(f"Connecting to TraCI on port {args.port} ...")
        for attempt in range(30):
            try:
                traci.init(args.port)
                break
            except traci.exceptions.FatalTraCIError:
                if attempt == 29:
                    raise
                time.sleep(1.0)
        print("Connected.")
    else:
        binary = sumo_bin("sumo-gui" if args.gui else "sumo")
        cmd = [
            binary,
            "-c",
            str(SUMOCFG),
            "-b",
            str(args.begin),
            "--step-length",
            str(args.step_length),
            "--start",
            "--delay",
            str(args.delay),
            "--no-step-log",
            "--duration-log.disable",
        ]
        print(f"Starting SUMO on TraCI port {args.port}:", " ".join(cmd))
        traci.start(cmd, port=args.port)

    try:
        if args.jump_to is not None and args.jump_to > traci.simulation.getTime():
            print(f"Jumping to {args.jump_to:.0f}s ({_fmt_clock(args.jump_to)}) ...")
            step_to(traci, args.jump_to, chunk=args.chunk)
            print("Jump complete.")

        if args.emit:
            # Emitting path: run the loop inside an asyncio event loop so the
            # WebSocket server runs concurrently with the TraCI stepping.
            asyncio.run(_run_emitting(traci, args))
        else:
            print("Running simulation ...")
            while True:
                t = traci.simulation.getTime()
                if args.end is not None and t >= args.end:
                    break
                if traci.simulation.getMinExpectedNumber() <= 0 and t >= (args.jump_to or 0):
                    break
                traci.simulationStep()
                if int(t) % 60 == 0:
                    _print_status(traci)
    except KeyboardInterrupt:
        print("\nStopped by user.")
    finally:
        traci.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
