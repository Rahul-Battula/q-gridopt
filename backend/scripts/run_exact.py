"""Exact enumeration of discrete battery paths for every tier, compared with the LP.

Run from the project root (cmd):
    python backend\\scripts\\run_exact.py [preset_id]      (default: scenario_b)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classical.exact import enumerate_paths, solve_exact  # noqa: E402
from app.classical.lp import solve_lp  # noqa: E402
from app.grid.presets import DEFAULT_PRESET, load_preset  # noqa: E402
from app.grid.tiers import TIERS  # noqa: E402

TOP = 8

preset = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PRESET
sc = load_preset(preset)
lp = solve_lp(sc).evaluation.objective
print(f"===== {sc.name} ({preset}) | LP optimum (continuous): ${lp:,.0f} =====")

for tier, levels in TIERS.items():
    r = solve_exact(sc, levels, tier)
    d = r.details
    print(f"\n[{tier}] levels {d['levels']} | {d['n_paths']} paths, {d['n_feasible']} feasible"
          f" | {r.provenance.solve_time_s * 1000:.0f} ms")
    print(f"  best path {d['best_path']} -> ${r.evaluation.objective:,.0f}"
          f" (gap to LP ${r.evaluation.objective - lp:,.0f})"
          f" | optimal paths: {len(d['optimal_paths'])}"
          f" | mean feasible ${d['mean_feasible_objective']:,.0f}"
          f" | worst feasible ${d['worst_feasible_objective']:,.0f}")
    print(f"  top {TOP}:")
    for rank, s in enumerate(enumerate_paths(sc, levels)[:TOP], 1):
        flag = "" if s.feasible else f"  INFEASIBLE {s.violations}"
        print(f"    {rank:>2}. SOC {str([int(x) for x in s.path]):<14} ${s.objective:>9,.0f}{flag}")
