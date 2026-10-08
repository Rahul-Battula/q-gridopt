"""Print the Stage 1 results: each preset, with and without the battery.

Run from the project root (cmd):
    python backend\\scripts\\show_stage1.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.dispatch import dispatch_from_soc_path, dispatch_no_battery  # noqa: E402
from app.grid.evaluator import evaluate  # noqa: E402
from app.grid.presets import list_presets  # noqa: E402


def show(title, scenario, schedule):
    ev = evaluate(scenario, schedule)
    print(f"\n{title}")
    print(f"  {'Period':<10}{'solar':>7}{'wind':>6}{'gas':>6}{'chg':>6}{'dis':>6}{'unsrv':>7}{'SOC':>6}{'curt':>6}{'cost $':>9}")
    for p, x, m in zip(scenario.periods, schedule.periods, ev.periods):
        print(f"  {p.name:<10}{x.solar:>7g}{x.wind:>6g}{x.gas:>6g}{x.charge:>6g}{x.discharge:>6g}"
              f"{x.unserved:>7g}{m.soc_end:>6g}{m.curtailment:>6g}{m.total_cost:>9,.0f}")
    print(f"  objective ${ev.objective:,.0f} = gas ${ev.gas_cost:,.0f} + CO2 ${ev.co2_cost:,.0f}"
          f" + curtail ${ev.curtailment_cost:,.0f} + wear ${ev.wear_cost:,.0f}"
          f" + unserved ${ev.unserved_cost:,.0f}")
    print(f"  CO2 {ev.co2_tonnes:g} t | curtailment {ev.curtailment_mwh:g} MWh"
          f" | renewable use {ev.renewable_utilization:.1%} | feasible: {ev.feasible}")


for pid, sc in list_presets().items():
    print(f"\n===== {sc.name} ({pid}) =====")
    show("No battery:", sc, dispatch_no_battery(sc))
    show("Battery path SOC 0 -> 20 -> 0 (store afternoon surplus, use in evening):",
         sc, dispatch_from_soc_path(sc, [0, 20, 0]))
