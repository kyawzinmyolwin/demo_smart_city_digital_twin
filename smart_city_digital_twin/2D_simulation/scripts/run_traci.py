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
import sys
import time

from _sim_root import SIM_ROOT  # noqa: E402
from sim_pipeline import SUMOCFG, setup_sumolib, sumo_bin

# Earliest vehicle depart in data/output/demand/traffic_trips.routed.rou.xml (06:30).
DEFAULT_JUMP_TO = 23400.0
DEFAULT_PORT = 8813


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
    return p


def main() -> int:
    args = build_parser().parse_args()
    if setup_sumolib() is None:
        print("missing SUMO install (expected C:\\Sumo)", file=sys.stderr)
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
