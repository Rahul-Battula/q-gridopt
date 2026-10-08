r"""Grover adaptive search vs classical search: how many cost-function queries to find the optimal plan?

Run from the project root (cmd):
    python backend\scripts\run_grover.py [--trials 200] [--max-hours 15] [--seed 1234] [--qiskit-check]

What is measured (all in the same unit, one QUERY = one evaluation of the cost function):
  * GAS      Grover adaptive search (oracle = Qiskit DiagonalGate, threshold lowered after every improvement)
  * blind    classical random search over ALL 2^n bitstrings (what Grover is provably quadratically faster than)
  * structured  classical search that only tries the VALID battery plans (exploits the problem structure)
and, separately, classical dynamic programming (polynomial in the number of hours; not a query search).
Writes data/benchmarks/grover.json and grover.md. The statevector evolution is exact (closed form, checked
against the Qiskit circuit in tests/test_grover.py), so Q18 and 15-hour grids are simulated exactly too.
"""

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.grid.presets import load_preset  # noqa: E402
from app.provenance import library_versions, utc_now  # noqa: E402
from app.quantum import grover  # noqa: E402
from app.quantum.qubo import build_qubo  # noqa: E402
from app.quantum.transpile import DEFAULT_FAKE_BACKEND, circuit_stats, fake_backend, transpile_for_backend  # noqa: E402
from app.models.grid import Period, Scenario  # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "data" / "benchmarks"


def varied_scenario(hours: int, seed: int = 11) -> Scenario:
    """A grid with `hours` DIFFERENT hours (random demand / solar / wind in 5 MW steps), so the optimal plan is
    unique. (Repeating one 3-hour pattern would create many tied optimal plans and blur the scaling.)"""
    base = load_preset("scenario_b")
    rng = np.random.default_rng(seed)

    def r(lo: float, hi: float) -> float:
        return float(5 * round(rng.uniform(lo, hi) / 5))

    periods = [Period(name=f"H{i + 1}", demand=r(60, 160), solar=r(0, 150), wind=r(0, 60)) for i in range(hours)]
    return Scenario(name=f"Random grid x {hours}h", description="random hours, unique optimum",
                    periods=periods, gas_max=base.gas_max, battery=base.battery, costs=base.costs)


def valid_plan_count(model) -> int:
    levels = len(model.levels)
    return levels ** model.num_periods


def one_iteration_cost(num_qubits: int, energies: np.ndarray) -> dict:
    """Gate cost of ONE oracle + diffuser on a Heron chip, with a single marked state (the late-search case)."""
    marked = np.array([int(np.argmin(energies))])
    qc = grover.grover_circuit(num_qubits, marked, 1)
    qc.measure_all()
    backend = fake_backend(DEFAULT_FAKE_BACKEND)
    stats = circuit_stats(transpile_for_backend(qc, backend, 1))
    return {"backend": DEFAULT_FAKE_BACKEND, "two_qubit_gates": stats["two_qubit_gates"], "depth": stats["depth"]}


def exponent(rows: list[dict], key: str) -> float:
    """Slope of log2(mean queries) against qubits: 1 = linear in N, 0.5 = sqrt(N)."""
    pts = [(r["qubits"], r[key]) for r in rows if r.get(key)]
    x, y = np.array([p[0] for p in pts], float), np.log2([p[1] for p in pts])
    return float(np.polyfit(x, y, 1)[0])


def fmt(v, digits=0):
    return "-" if v is None else f"{v:,.{digits}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--trials", type=int, default=200)
    ap.add_argument("--max-hours", type=int, default=15)
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--qiskit-check", action="store_true", help="also run Q3 GAS with real Qiskit circuits")
    args = ap.parse_args()

    base = load_preset("scenario_b")
    results = {"created_at": utc_now(), "preset": "scenario_b", "trials": args.trials, "seed": args.seed,
               "versions": library_versions("qiskit", "qiskit-aer", "numpy"), "tiers": [], "chain": []}

    print("== the three project tiers (Scenario B) ==")
    for tier in ("Q3", "Q9", "Q18"):
        model = build_qubo(base, tier)
        e = model.energies_all()
        stats = grover.run_trials(e, valid_plan_count(model), args.trials, args.seed)
        stats["tier"] = tier
        if tier in ("Q3", "Q9"):
            stats["one_iteration"] = one_iteration_cost(model.num_qubits, e)
        results["tiers"].append(stats)
        print(f"{tier}: N={stats['states']:,} GAS {fmt(stats['gas_queries_mean'], 1)} q | blind "
              f"{fmt(stats['random_unstructured_without_replacement_mean'], 1)} q | structured "
              f"{fmt(stats['classical_structured_mean'], 1)} q | success {stats['gas_success_rate']:.0%}")

    print("== Q3 encoding, grid with more hours (every bitstring is a valid plan) ==")
    for hours in range(3, args.max_hours + 1):
        model = build_qubo(varied_scenario(hours), "Q3")
        e = model.energies_all()
        stats = grover.run_trials(e, valid_plan_count(model), args.trials, args.seed)
        stats["hours"] = hours
        results["chain"].append(stats)
        print(f"{hours:>2} h: N={stats['states']:>6,} GAS {fmt(stats['gas_queries_mean'], 1):>8} q | blind "
              f"{fmt(stats['random_unstructured_without_replacement_mean'], 1):>9} q | speedup "
              f"{fmt(stats['speedup_vs_unstructured'], 2)}x | success {stats['gas_success_rate']:.0%}")

    chain = results["chain"]
    results["exponent_gas"] = exponent(chain, "gas_queries_mean")
    results["exponent_blind"] = exponent(chain, "random_unstructured_without_replacement_mean")
    crossover = next((r["hours"] for r in chain if r["speedup_vs_unstructured"] and r["speedup_vs_unstructured"] > 1), None)
    results["first_hours_with_speedup"] = crossover
    print(f"exponents (queries ~ N^x): GAS {results['exponent_gas']:.2f}, blind {results['exponent_blind']:.2f}; "
          f"GAS first beats blind search at {crossover} hours")

    if args.qiskit_check:
        e = build_qubo(base, "Q3").energies_all()
        wins = sum(grover.grover_adaptive_search(e, np.random.default_rng(s), 500, "qiskit", 3).found for s in range(20))
        results["qiskit_circuit_check"] = {"tier": "Q3", "runs": 20, "found_optimum": wins}
        print(f"Q3 GAS driven by real Qiskit circuits: optimum found in {wins}/20 runs")

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "grover.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    (OUT / "grover.md").write_text(markdown(results), encoding="utf-8")
    print(f"wrote {OUT / 'grover.md'}")


def markdown(r: dict) -> str:
    lines = [
        "# Grover adaptive search: query counts vs classical search",
        "",
        f"Generated {r['created_at']} · {r['trials']} independent runs per row · seed {r['seed']} · "
        f"preset {r['preset']} · one query = one evaluation of the cost function.",
        "",
        "**What this shows.** Grover's algorithm needs about sqrt(N) queries where a classical unstructured search "
        "needs about N/2. The speedup is real and provable, but it is a speedup over *unstructured search of the "
        "qubit bitstring space*. A classical method that exploits the structure of the battery problem "
        "(try only valid plans, or dynamic programming) needs far fewer queries, so **no advantage over the best "
        "classical solver is claimed**. It also needs a fault-tolerant machine to run at useful sizes.",
        "",
        "## The three project tiers",
        "",
        "| Tier | Qubits | Bitstrings N | Valid plans | Grover (queries) | Blind search of N | Speedup vs blind | "
        "Structured classical | Speedup vs structured | Success | Oracle+diffuser on FakeFez (2q gates) |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in r["tiers"]:
        it = t.get("one_iteration")
        lines.append(
            f"| {t['tier']} | {t['qubits']} | {t['states']:,} | {t['valid_plans']:,} | {fmt(t['gas_queries_mean'], 1)} | "
            f"{fmt(t['random_unstructured_without_replacement_mean'], 1)} | {fmt(t['speedup_vs_unstructured'], 2)}x | "
            f"{fmt(t['classical_structured_mean'], 1)} | {fmt(t['speedup_vs_structured'], 2)}x | "
            f"{t['gas_success_rate']:.0%} | {it['two_qubit_gates'] if it else 'not run'} |")
    lines += [
        "",
        "## Scaling: Q3 encoding, grids with more hours (random hours, seed 11)",
        "",
        "Every bitstring is a valid plan here, so blind search and enumeration are the same classical baseline.",
        "",
        "| Hours = qubits | N = 2^n | Optimal plans | Grover (queries) | Blind search | Speedup | Success |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in r["chain"]:
        lines.append(f"| {c['hours']} | {c['states']:,} | {c['optimal_states']} | {fmt(c['gas_queries_mean'], 1)} | "
                     f"{fmt(c['random_unstructured_without_replacement_mean'], 1)} | "
                     f"{fmt(c['speedup_vs_unstructured'], 2)}x | {c['gas_success_rate']:.0%} |")
    lines += [
        "",
        f"Fitted scaling, queries ~ N^x: Grover x = {r['exponent_gas']:.2f}, blind classical x = {r['exponent_blind']:.2f} "
        f"(theory: 0.5 and 1.0). Grover first needs fewer queries than blind search at "
        f"{r['first_hours_with_speedup']} hours.",
        "",
        "## Honest caveats",
        "",
        "- The fitted slopes sit below 0.5 / 1.0 partly because the number of tied optimal plans grows with the grid, "
        "which makes every search easier; read the speedup column, not the slopes, as the evidence.",
        "- Below the break-even size, unknown-M Grover search is *slower* than just trying bitstrings (its constant factor is large).",
        "- The battery problem is a chain: classical dynamic programming solves it in polynomial time "
        "(see scaling.md), which beats any search, quantum or classical.",
        "- An oracle call here is one coherent cost evaluation. Building that oracle as a real reversible circuit, "
        "and running it error-corrected, is what a hardware advantage would require; on today's chips the "
        "oracle alone costs far more gates than can run before noise dominates (last column).",
        "- The statevector evolution is exact (closed form, verified against the Qiskit circuit in tests); "
        "no quantum computer produced these query counts.",
    ]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    main()
