r"""Extended model study: unit commitment, forecast uncertainty and a reserve margin.

Run from the project root (cmd):
    python backend\scripts\run_extended.py [--no-noise] [--p 3]

Part A  what each feature changes: Scenario B, then + unit commitment, + forecast uncertainty,
        + reserve (= Scenario C). For each: the greedy no-battery baseline, the exact optimum of the
        discrete problem, the continuous MILP optimum, and the plan.
Part B  QAOA vs classical on Scenario C: Q3U (12 qubits) and Q9U (18 qubits).
Writes data/benchmarks/extended.json and extended.md. QAOA time is classical simulation time.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classical.annealing import solve_annealing  # noqa: E402
from app.classical.exact import solve_exact  # noqa: E402
from app.classical.lp import solve_lp  # noqa: E402
from app.classical.no_battery import solve_no_battery  # noqa: E402
from app.grid.presets import load_preset  # noqa: E402
from app.grid.tiers import TIERS  # noqa: E402
from app.provenance import utc_now  # noqa: E402
from app.quantum.simulate import run_depth_sweep, run_noisy_simulation  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "benchmarks"


def onoff(commits):
    return "-" if commits is None else " ".join("on" if c else "off" for c in commits)


def part_a() -> list[dict]:
    full = load_preset("scenario_c")
    base = load_preset("scenario_b")
    variants = [
        ("Scenario B (base model)", base),
        ("+ unit commitment", base.model_copy(update={"unit_commitment": full.unit_commitment})),
        ("+ forecast uncertainty", base.model_copy(update={"unit_commitment": full.unit_commitment,
                                                           "uncertainty": full.uncertainty})),
        ("+ reserve margin (Scenario C)", full),
    ]
    rows = []
    for name, sc in variants:
        tier = "Q3U" if sc.unit_commitment else "Q3"
        exact = solve_exact(sc, TIERS[tier], tier)
        lp = solve_lp(sc)
        nb = solve_no_battery(sc)
        e = exact.evaluation
        rows.append({
            "model": name, "tier": tier,
            "no_battery": nb.evaluation.objective, "exact": e.objective, "milp": lp.evaluation.objective,
            "plan": exact.details["best_path"], "gas": onoff(exact.details["best_commits"]),
            "startups": e.startups, "startup_cost": e.startup_cost, "reserve_cost": e.reserve_cost,
            "worst_case": e.worst_case_objective, "unserved_mwh": e.unserved_mwh,
        })
        print(f"A  {name:34s} exact {e.objective:10,.1f}  MILP {lp.evaluation.objective:10,.1f}  "
              f"no-battery {nb.evaluation.objective:10,.1f}  plan {exact.details['best_path']} gas {rows[-1]['gas']}")
    return rows


def part_b(max_p: int, noise: bool) -> list[dict]:
    sc = load_preset("scenario_c")
    rows = []
    for tier in ("Q3U", "Q9U"):
        exact = solve_exact(sc, TIERS[tier], tier)
        sa = solve_annealing(sc, tier)
        sweep = run_depth_sweep(sc, tier, max_p)
        for r in sweep:
            d = r.details
            q, rnd = d["qaoa_exact"], d["random_exact"]
            row = {"tier": tier, "qubits": d["num_qubits"], "p": d["reps"], "p_valid": q["p_valid"],
                   "p_optimal": q["p_optimal"], "random_p_optimal": rnd["p_optimal"],
                   "ar": q["approximation_ratio"], "two_qubit_gates": d["circuit"]["transpiled"]["two_qubit_gates"],
                   "best_found": d["best_found"], "optimal": d["optimal_objective"],
                   "annealing_p_optimal": sa.details["qaoa_sampled"]["p_optimal"],
                   "annealing_best": sa.details["best_found"], "exact_best": exact.details["best_path"],
                   "exact_gas": onoff(exact.details["best_commits"]), "noisy_p_optimal": None}
            if noise and tier == "Q3U":
                row["noisy_p_optimal"] = run_noisy_simulation(sc, r).details["qaoa_sampled"]["p_optimal"]
            rows.append(row)
            print(f"B  {tier} p={d['reps']} valid {q['p_valid']:6.1%} P(opt) {q['p_optimal']:6.2%} "
                  f"(random {rnd['p_optimal']:.4%}, annealing {row['annealing_p_optimal']:.2%}) AR {q['approximation_ratio']:.3f} "
                  f"2q {row['two_qubit_gates']}" + (f" noisy P(opt) {row['noisy_p_optimal']:.2%}" if row["noisy_p_optimal"] is not None else ""),
                  flush=True)
    return rows


def to_markdown(a: list[dict], b: list[dict]) -> str:
    L = ["# Extended model study (unit commitment, forecast uncertainty, reserve)", "",
         f"Generated {utc_now()}. Costs in $ (expected value when the scenario has forecast cases).", "",
         "## A. What each feature changes", "",
         "| Model | Tier | No battery (greedy) | Exact optimum | MILP (continuous battery) | Best battery plan | Gas unit | Start-ups | Worst case |",
         "|---|---|---|---|---|---|---|---|---|"]
    for r in a:
        wc = "-" if r["worst_case"] is None else f"{r['worst_case']:,.0f}"
        L.append(f"| {r['model']} | {r['tier']} | {r['no_battery']:,.0f} | {r['exact']:,.0f} | {r['milp']:,.0f} | "
                 f"{[int(x) for x in r['plan']]} | {r['gas']} | {r['startups']} | {wc} |")
    L += ["", "## B. QAOA vs classical on Scenario C", "",
          "| Tier | Qubits | p | P(valid) | QAOA P(optimal) | Random P(optimal) | Annealing P(optimal) | Noisy sim P(optimal) | Approx. ratio | 2q gates (chip) | Best plan found |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in b:
        bf = r["best_found"]
        found = "none" if not bf else f"{[int(x) for x in bf['path']]} gas {onoff(bf.get('commits'))} ${bf['objective']:,.0f}"
        noisy = "-" if r["noisy_p_optimal"] is None else f"{r['noisy_p_optimal']:.2%}"
        L.append(f"| {r['tier']} | {r['qubits']} | {r['p']} | {r['p_valid']:.1%} | {r['p_optimal']:.2%} | "
                 f"{r['random_p_optimal']:.4%} | {r['annealing_p_optimal']:.2%} | {noisy} | {r['ar']:.3f} | "
                 f"{r['two_qubit_gates']} | {found} |")
    L.append("")
    return "\n".join(L)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--p", type=int, default=3)
    ap.add_argument("--no-noise", action="store_true")
    args = ap.parse_args()
    a = part_a()
    b = part_b(args.p, not args.no_noise)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "extended.json").write_text(json.dumps({"generated": utc_now(), "a": a, "b": b}, indent=2), encoding="utf-8")
    (OUT / "extended.md").write_text(to_markdown(a, b), encoding="utf-8")
    print(f"\nWrote {OUT / 'extended.md'}")


if __name__ == "__main__":
    main()
