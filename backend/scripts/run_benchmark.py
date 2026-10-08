"""Benchmark QAOA against classical methods on many random grid instances.

Run from the project root (cmd):
    python backend\\scripts\\run_benchmark.py                 (20 instances, Q3/Q9/Q18; ~25 min)
    python backend\\scripts\\run_benchmark.py --instances 5 --tiers Q3 Q9 --q18-qaoa 0   (quick)

Writes data\\benchmarks\\latest.md (results table), latest.json and a timestamped copy.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.benchmark.suite import run_suite, save, to_markdown  # noqa: E402

parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("--instances", type=int, default=20)
parser.add_argument("--tiers", nargs="+", default=["Q3", "Q9", "Q18"], choices=["Q3", "Q9", "Q18"])
parser.add_argument("--q18-qaoa", type=int, default=3, help="instances that also get QAOA on Q18 (slow)")
parser.add_argument("--shots", type=int, default=4096)
parser.add_argument("--max-reps", type=int, default=3, choices=[1, 2, 3])
parser.add_argument("--no-noise", action="store_true", help="skip the FakeFez noisy simulation")
args = parser.parse_args()

result = run_suite(instances=args.instances, tiers=tuple(args.tiers), qaoa_instances={"Q18": args.q18_qaoa},
                   noisy_tiers=() if args.no_noise else ("Q3", "Q9"), shots=args.shots, max_reps=args.max_reps,
                   log=lambda msg: print(msg, flush=True))
paths = save(result)
print()
print(to_markdown(result))
print(f"Saved: {paths['latest_md']}\n       {paths['json']}")
