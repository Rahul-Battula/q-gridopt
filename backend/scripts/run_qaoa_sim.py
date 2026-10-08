"""QAOA (p = 1..3) on the ideal Aer simulator vs uniform random sampling.

Run from the project root (cmd):
    python backend\\scripts\\run_qaoa_sim.py                      (scenario_b, Q3 and Q9)
    python backend\\scripts\\run_qaoa_sim.py scenario_b Q3 Q9 Q18  (Q18 takes a few minutes)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.presets import load_preset  # noqa: E402
from app.quantum.simulate import run_depth_sweep  # noqa: E402

preset = sys.argv[1] if len(sys.argv) > 1 else "scenario_b"
tiers = sys.argv[2:] or ["Q3", "Q9"]
sc = load_preset(preset)


def pct(x):
    return f"{100 * x:6.2f}%"


for tier in tiers:
    results = run_depth_sweep(sc, tier, max_reps=3)
    d0 = results[0].details
    rnd = d0["random_exact"]
    print(f"\n===== {sc.name} | {tier} ({d0['num_qubits']} qubits) | optimum ${d0['optimal_objective']:,.0f}"
          f" | penalty A ${d0['penalty']:,.0f} =====")
    print(f"  uniform random (exact): P(optimal) {pct(rnd['p_optimal'])}  P(valid) {pct(rnd['p_valid'])}"
          f"  P(feasible) {pct(rnd['p_feasible'])}")
    rb = d0["random_best_found"]
    print(f"  uniform random ({results[0].provenance.shots} shots): P(optimal) {pct(d0['random_sampled']['p_optimal'])}"
          f"  best found {rb['path'] if rb else None} ${rb['objective'] if rb else float('nan'):,.0f}")
    print(f"  {'p':>2} {'<E> $':>11} {'P(opt) exact':>13} {'P(opt) shots':>13} {'P(valid)':>9} {'P(feas)':>9}"
          f" {'x random':>9} {'best found':>22} {'evals':>6} {'train s':>8}")
    for r in results:
        d = r.details
        ex, sm, bf = d["qaoa_exact"], d["qaoa_sampled"], d["best_found"]
        lift = ex["p_optimal"] / rnd["p_optimal"] if rnd["p_optimal"] else float("nan")
        best = f"{[int(v) for v in bf['path']]} ${bf['objective']:,.0f}" if bf else "none feasible"
        print(f"  {d['reps']:>2} {d['training']['expected_energy_dollars']:>11,.0f} {pct(ex['p_optimal']):>13}"
              f" {pct(sm['p_optimal']):>13} {pct(ex['p_valid']):>9} {pct(ex['p_feasible']):>9} {lift:>8.1f}x"
              f" {best:>22} {d['training']['evaluations']:>6} {d['training']['seconds']:>8.1f}")
    top = results[-1].details["qaoa_exact"]["top_paths"]
    print(f"  most likely paths at p=3: " + ", ".join(
        f"{[int(v) for v in t['path']]} {pct(t['probability']).strip()}" for t in top[:3]))
