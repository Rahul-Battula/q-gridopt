r"""Standard X mixer vs ring XY mixer on the one-hot tiers (ideal simulator, exact probabilities).

Run from the project root (cmd):
    python backend\scripts\run_mixer_compare.py [tier ...]       (default: Q9)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.presets import load_preset  # noqa: E402
from app.quantum.simulate import run_qaoa_simulation  # noqa: E402

tiers = sys.argv[1:] or ["Q9"]
sc = load_preset("scenario_b")
for tier in tiers:
    print(f"\n=== {tier}, Scenario B ===")
    print(f"{'mixer':>5} {'p':>2} | {'P(valid)':>8} {'P(opt)':>8} {'AR(all)':>8} {'AR(feasible)':>12} | "
          f"{'2q on chip':>10} {'depth':>6} | {'train s':>7}")
    for mixer in ("x", "xy"):
        warm = None
        for reps in (1, 2, 3):
            r, warm = run_qaoa_simulation(sc, tier, reps, warm_start=warm, mixer=mixer)
            d = r.details
            q, c = d["qaoa_exact"], d["circuit"]["transpiled"]
            arf = q["approximation_ratio_feasible"]
            print(f"{mixer:>5} {reps:>2} | {q['p_valid']:8.1%} {q['p_optimal']:8.2%} {q['approximation_ratio']:8.3f} "
                  f"{arf if arf is None else format(arf, '12.3f')} | {c['two_qubit_gates']:>10} {c['depth']:>6} | "
                  f"{r.provenance.solve_time_s:7.1f}")
