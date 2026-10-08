"""QAOA ideal vs noisy (IBM device noise model), with circuit sizes and approximation ratios.

Run from the project root (cmd):
    python backend\\scripts\\run_noisy_sim.py                          (scenario_b, Q3 and Q9, FakeFez)
    python backend\\scripts\\run_noisy_sim.py scenario_b FakeFez Q3 Q9 Q18
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.presets import load_preset  # noqa: E402
from app.quantum.simulate import run_depth_sweep, run_noisy_simulation  # noqa: E402

preset = sys.argv[1] if len(sys.argv) > 1 else "scenario_b"
backend = sys.argv[2] if len(sys.argv) > 2 else "FakeFez"
tiers = sys.argv[3:] or ["Q3", "Q9"]
sc = load_preset(preset)


def pct(x):
    return f"{100 * x:5.1f}%"


for tier in tiers:
    ideal_runs = run_depth_sweep(sc, tier, max_reps=3)
    d0 = ideal_runs[0].details
    rnd = d0["random_exact"]
    print(f"\n===== {sc.name} | {tier} ({d0['num_qubits']} qubits) | noise model {backend}"
          f" | optimum ${d0['optimal_objective']:,.0f} | worst feasible ${d0['worst_feasible_objective']:,.0f} =====")
    print(f"  uniform random: P(opt) {pct(rnd['p_optimal'])}  P(feasible) {pct(rnd['p_feasible'])}"
          f"  AR {rnd['approximation_ratio']:.3f}")
    print(f"  {'p':>2} | {'logical':>14} | {'on chip':>14} || {'P(opt)':>15} | {'P(feasible)':>15} |"
          f" {'AR (all shots)':>15} | {'AR feas.':>11} | {'noisy best found':>18}")
    print(f"  {'':>2} | {'depth / 2q':>14} | {'depth / 2q':>14} || {'ideal  noisy':>15} | {'ideal  noisy':>15} |"
          f" {'ideal  noisy':>15} | {'ideal noisy':>11} |")
    for ideal in ideal_runs:
        noisy = run_noisy_simulation(sc, ideal, backend_name=backend)
        di, dn = ideal.details, noisy.details
        ie, ns = di["qaoa_exact"], dn["qaoa_sampled"]
        lg, tc = di["circuit"]["logical"], dn["circuit"]["transpiled"]
        bf = dn["best_found"]
        best = f"{[int(v) for v in bf['path']]} ${bf['objective']:,.0f}" if bf else "none feasible"
        print(f"  {di['reps']:>2} | {lg['depth']:>6} / {lg['two_qubit_gates']:<5} | {tc['depth']:>6} / {tc['two_qubit_gates']:<5} ||"
              f" {pct(ie['p_optimal'])} {pct(ns['p_optimal'])} | {pct(ie['p_feasible'])} {pct(ns['p_feasible'])} |"
              f" {ie['approximation_ratio']:6.3f} {ns['approximation_ratio']:6.3f}   |"
              f" {ie['approximation_ratio_feasible']:.2f}  {ns['approximation_ratio_feasible'] or 0:.2f} | {best:>18}")
