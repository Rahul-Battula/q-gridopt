"""Run the classical solvers on every preset and print a comparison.

Run from the project root (cmd):
    python backend\\scripts\\run_classical.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classical.lp import solve_lp  # noqa: E402
from app.classical.no_battery import solve_no_battery  # noqa: E402
from app.grid.presets import list_presets  # noqa: E402

for pid, sc in list_presets().items():
    print(f"\n===== {sc.name} ({pid}) =====")
    for result in (solve_lp(sc), solve_no_battery(sc)):
        ev = result.evaluation
        print(f"\n[{result.source}] {result.provenance.method} | {result.provenance.backend}"
              f" | {result.provenance.solve_time_s * 1000:.1f} ms")
        print(f"  {'Period':<10}{'solar':>7}{'wind':>6}{'gas':>6}{'chg':>6}{'dis':>6}{'SOC':>6}{'curt':>6}")
        for p, x, m in zip(sc.periods, result.schedule.periods, ev.periods):
            print(f"  {p.name:<10}{x.solar:>7g}{x.wind:>6g}{x.gas:>6g}{x.charge:>6g}"
                  f"{x.discharge:>6g}{m.soc_end:>6g}{m.curtailment:>6g}")
        print(f"  objective ${ev.objective:,.0f} | CO2 {ev.co2_tonnes:g} t"
              f" | curtailment {ev.curtailment_mwh:g} MWh | feasible: {ev.feasible}")

    saving = solve_no_battery(sc).evaluation.objective - solve_lp(sc).evaluation.objective
    print(f"\n  Battery saves ${saving:,.0f} vs no battery")
