"""Time pipeline scripts. Usage: python bench_build_simulation.py [label] [--with-duarouter]"""

from __future__ import annotations



import subprocess

import sys

import time

from pathlib import Path

from _sim_root import SIM_ROOT

PY = sys.executable
CREATE_NETWORK = SIM_ROOT / "scripts/create_network.py"
CREATE_DEMAND = SIM_ROOT / "scripts/create_demand.py"





def run_script(script: Path, extra_argv: list[str], label: str) -> float:

    cmd = [PY, str(script), *extra_argv]

    print(f"\n--- {label} ---")

    print(" ".join(cmd))

    t0 = time.perf_counter()

    rc = subprocess.run(cmd, cwd=str(SIM_ROOT)).returncode

    elapsed = time.perf_counter() - t0

    print(f"{label}: {elapsed:.1f}s (exit {rc})")

    return elapsed if rc == 0 else -elapsed





def main() -> int:

    label = sys.argv[1] if len(sys.argv) > 1 else "run"

    results: dict[str, float] = {}



    results["map"] = run_script(

        CREATE_NETWORK, ["--only", "map", "--skip-network"], "map"

    )

    results["trips"] = run_script(CREATE_DEMAND, ["--only", "trips"], "trips")

    if "--with-duarouter" in sys.argv:

        results["duarouter_1"] = run_script(

            CREATE_DEMAND,

            ["--only", "duarouter", "--skip-trips"],

            "duarouter (1 thread)",

        )

        results["duarouter_4"] = run_script(

            CREATE_DEMAND,

            ["--only", "duarouter", "--skip-trips", "--routing-threads", "4"],

            "duarouter (4 threads)",

        )



    print(f"\n=== Summary ({label}) ===")

    for k, v in results.items():

        sign = "" if v >= 0 else "FAILED "

        print(f"  {k}: {sign}{abs(v):.1f}s")



    d1, d4 = results.get("duarouter_1"), results.get("duarouter_4")

    if d1 and d4 and d1 > 0 and d4 > 0:

        saved = d1 - d4

        pct = 100.0 * saved / d1

        print(f"  duarouter speedup (4 threads): {saved:.1f}s ({pct:.0f}% faster)")



    return 0





if __name__ == "__main__":

    raise SystemExit(main())

