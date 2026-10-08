r"""Scaling study: what happens as the grid gets more hours (more qubits)?

Run from the project root (cmd):
    python backend\scripts\\run_scaling.py [--max-q3-hours 15] [--q9-hours 3 4 5]

For each size it reports
  * QUBO size (qubits, Ising terms)
  * circuit size for p = 1 after transpiling for an IBM Heron chip (FakeFez)
  * QAOA p = 1 (ideal simulator, trained angles) success probability vs uniform random guessing
  * classical cost: exhaustive enumeration (grows exponentially) AND dynamic programming over the
    battery level (grows linearly in hours). The battery problem is a CHAIN, so a classical
    polynomial-time algorithm exists. This is the key honest point against any advantage claim.
Writes data/benchmarks/scaling.json and scaling.md. QAOA time is classical simulation time.
"""

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.classical.exact import enumerate_paths  # noqa: E402
from app.grid.presets import load_preset  # noqa: E402
from app.grid.tiers import TIERS  # noqa: E402
from app.models.grid import Period, Scenario  # noqa: E402
from app.provenance import utc_now  # noqa: E402
from app.quantum import decoder  # noqa: E402
from app.quantum.qaoa import train  # noqa: E402
from app.quantum.qubo import build_qubo, period_energy  # noqa: E402
from app.quantum.simulate import circuit_report, cost_for  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "benchmarks"


def long_scenario(hours: int) -> Scenario:
    """Scenario B's morning / afternoon / evening pattern repeated for `hours` hours."""
    base = load_preset("scenario_b")
    periods = [base.periods[i % 3].model_copy(update={"name": f"H{i + 1}"}) for i in range(hours)]
    return Scenario(name=f"Scenario B x {hours}h", description="repeating 3-hour pattern",
                    periods=periods, gas_max=base.gas_max, battery=base.battery, costs=base.costs)


def dp_optimum(sc: Scenario, levels: tuple[float, ...]) -> tuple[float, float]:
    """Classical dynamic programming over the battery level: O(hours x levels^2). (cost, seconds)."""
    start = time.perf_counter()
    inf = float("inf")
    best = {sc.battery.initial_soc: 0.0}
    for t in range(len(sc.periods)):
        nxt = {}
        for b in levels:
            cands = []
            for a, cost_a in best.items():
                cost, bad = period_energy(sc, t, b - a)
                if not bad:
                    cands.append(cost_a + cost)
            nxt[b] = min(cands) if cands else inf
        best = nxt
    return min(best.values()), time.perf_counter() - start


def study_one(tier: str, hours: int, train_qaoa: bool) -> dict:
    sc, levels = long_scenario(hours), TIERS[tier]
    model, cost = cost_for(sc, tier, None)
    row = {"tier": tier, "hours": hours, "qubits": model.num_qubits,
           "ising_terms": len(cost.hamiltonian.paulis), "levels": len(levels), "paths": len(levels) ** hours}

    circ = circuit_report(cost, 1)
    row.update(logical_2q=circ["logical"]["two_qubit_gates"], transpiled_2q=circ["transpiled"]["two_qubit_gates"],
               transpiled_depth=circ["transpiled"]["depth"])

    start = time.perf_counter()
    feasible = [s for s in enumerate_paths(sc, levels) if s.feasible]
    row["enumeration_s"] = time.perf_counter() - start
    optimum = min(s.objective for s in feasible)
    dp_cost, row["dp_s"] = dp_optimum(sc, levels)
    row["dp_matches_enumeration"] = abs(dp_cost - optimum) < 1e-6
    row["optimum"] = optimum

    if train_qaoa:
        table = decoder.path_table(sc, model)
        n_opt = sum(1 for i in table.values() if i.feasible and i.objective <= optimum + 1e-6)
        start = time.perf_counter()
        trained = train(cost, 1)
        from app.quantum import aer_runner
        from app.quantum.qaoa import build_ansatz, parameter_values
        circuit = build_ansatz(cost, 1)
        probs = aer_runner.exact_probabilities(circuit, parameter_values(circuit, trained.gammas, trained.betas))
        stats = decoder.distribution_stats(probs, table)
        row.update(qaoa_p_optimal=stats["p_optimal"], qaoa_p_valid=stats["p_valid"],
                   random_p_optimal=n_opt / 2 ** model.num_qubits, n_optimal_paths=n_opt,
                   qaoa_train_s=time.perf_counter() - start)
    return row


def to_markdown(rows: list[dict]) -> str:
    def f(v, spec):
        return "-" if v is None else format(v, spec)

    lines = ["# Scaling study: more hours, more qubits", "",
             f"Generated {utc_now()}. Grid = Scenario B pattern repeated; QAOA p = 1, ideal simulator; "
             "circuits transpiled for FakeFez (IBM Heron). QAOA time is classical simulation time.", "",
             "| Tier | Hours | Qubits | Ising terms | 2q gates (on chip) | Depth (on chip) | "
             "QAOA P(optimal) | Random P(optimal) | Enumeration s | Dynamic programming s |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(f"| {r['tier']} | {r['hours']} | {r['qubits']} | {r['ising_terms']} | {r['transpiled_2q']} | "
                     f"{r['transpiled_depth']} | {f(r.get('qaoa_p_optimal'), '.2%')} | "
                     f"{f(r.get('random_p_optimal'), '.4%')} | {r['enumeration_s']:.3f} | {r['dp_s']:.5f} |")
    ok = all(r["dp_matches_enumeration"] for r in rows)
    lines += ["", f"Dynamic programming matched exhaustive enumeration on every row: **{ok}**.", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-q3-hours", type=int, default=15)
    ap.add_argument("--q9-hours", type=int, nargs="*", default=[3, 4, 5])
    ap.add_argument("--max-qaoa-qubits", type=int, default=15)
    args = ap.parse_args()

    plan = [("Q3", h) for h in range(3, args.max_q3_hours + 1)] + [("Q9", h) for h in args.q9_hours]
    rows = []
    for tier, hours in plan:
        n = hours * (1 if tier == "Q3" else 3)
        print(f"{tier} {hours}h ({n} qubits) ...", flush=True)
        rows.append(study_one(tier, hours, train_qaoa=n <= args.max_qaoa_qubits))
        print("   ", {k: (round(v, 4) if isinstance(v, float) else v) for k, v in rows[-1].items()}, flush=True)

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "scaling.json").write_text(json.dumps({"generated": utc_now(), "rows": rows}, indent=2), encoding="utf-8")
    (OUT / "scaling.md").write_text(to_markdown(rows), encoding="utf-8")
    print(f"\nWrote {OUT / 'scaling.md'}")


if __name__ == "__main__":
    main()
