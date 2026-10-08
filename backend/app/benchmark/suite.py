"""Benchmark suite: many random grid instances, every method, one results table.

For each random 3-hour instance and each tier (Q3 / Q9 / Q18) we run:
  exact       exhaustive enumeration of the discrete problem (ground truth)
  lp          continuous linear program (CBC); may beat the discrete levels, never worse
  no_battery  greedy dispatch with the battery idle ("always idle" reference)
  annealing   simulated annealing on the same QUBO, same number of samples as QAOA shots
  random      uniform random bitstrings (analytic success probability)
  qaoa_ideal  QAOA p = 1..3 on the ideal Aer simulator (exact output probabilities)
  qaoa_noisy  same trained angles under an IBM device noise model (FakeFez), sampled

Every method gives two answers per instance: its top-1 plan (most likely valid plan) and its
best-of-N plan (best feasible sample). Classification-style metrics, mapped to scheduling:
  accuracy_top1 / accuracy_best  the answer is an optimal plan (feasible, cost = optimum)
  f1_top1 / f1_best              macro-F1 of the hourly battery DECISIONS (charge/idle/discharge)
                                 against the optimal plan's decisions, pooled over instances+hours
Distribution metrics for sampling methods:
  p_optimal        probability that ONE sample is an optimal plan ("success rate")
  approximation_ratio  (user-approved definition; invalid/rule-breaking samples count as worst)
  best_gap         $ above the optimum of the best feasible sample
  samples_99       samples needed for 99% confidence of hitting the optimum at least once:
                   ceil(ln 0.01 / ln(1 - p_optimal))   (hardware-independent time-to-solution)
  time_s           wall-clock seconds. For QAOA this is CLASSICAL SIMULATION time of training,
                   not QPU time, and is not a quantum speed measurement.
"""

import json
import math
import statistics
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

from app.classical.annealing import solve_annealing
from app.classical.exact import solve_exact
from app.classical.lp import solve_lp
from app.classical.no_battery import solve_no_battery
from app.grid.tiers import TIERS
from app.models.grid import Battery, CostWeights, Period, Scenario
from app.provenance import library_versions, utc_now
from app.quantum import decoder
from app.quantum.qubo import build_qubo
from app.quantum.simulate import run_depth_sweep, run_noisy_simulation

RESULTS_DIR = Path(__file__).resolve().parents[3] / "data" / "benchmarks"
PACKAGES = ("qiskit", "qiskit-aer", "qiskit-optimization", "qiskit-ibm-runtime", "pulp", "numpy", "scipy")


def random_scenario(seed: int) -> Scenario:
    """A plausible 3-hour grid: morning ramp, solar afternoon, evening peak. Values in steps of 5 MW."""
    rng = np.random.default_rng(seed)

    def r(lo: float, hi: float) -> float:
        return float(5 * round(rng.uniform(lo, hi) / 5))

    periods = [
        Period(name="Morning", demand=r(60, 120), solar=r(0, 60), wind=r(0, 60)),
        Period(name="Afternoon", demand=r(80, 160), solar=r(40, 160), wind=r(0, 60)),
        Period(name="Evening", demand=r(100, 180), solar=r(0, 30), wind=r(0, 60)),
    ]
    return Scenario(name=f"random-{seed}", description=f"Random benchmark instance (seed {seed})",
                    periods=periods, gas_max=100, battery=Battery(), costs=CostWeights())


def samples_99(p: float) -> float:
    if p >= 1.0:
        return 1.0
    if p <= 0.0:
        return math.inf
    return float(math.ceil(math.log(0.01) / math.log(1.0 - p)))


TOL = 1e-6
ACTIONS = ("charge", "idle", "discharge")


def battery_actions(path: list[float] | None, initial_soc: float, periods: int) -> list[str]:
    """The decision in each hour, read from the battery SOC path. 'none' = the method gave no plan."""
    if path is None:
        return ["none"] * periods
    prev, out = initial_soc, []
    for soc in path:
        out.append("charge" if soc > prev + TOL else "discharge" if soc < prev - TOL else "idle")
        prev = soc
    return out


def _plan(path, objective, feasible=True) -> dict:
    return {"path": [float(v) for v in path], "objective": float(objective), "feasible": bool(feasible)}


def _from_top(stats: dict) -> dict | None:
    """Most probable VALID plan of a distribution (top_paths is sorted by probability)."""
    top = stats["top_paths"]
    return _plan(top[0]["path"], top[0]["objective"], top[0]["feasible"]) if top else None


class _Ctx:
    """Per (instance, tier) ground truth used to score every method's answers."""

    def __init__(self, index: int, seed: int, tier: str, exact, initial_soc: float, periods: int):
        self.index, self.seed, self.tier = index, seed, tier
        self.opt = exact.evaluation.objective
        self.worst = exact.details["worst_feasible_objective"]
        self.optimal_paths = [[float(v) for v in p] for p in exact.details["optimal_paths"]]
        self.soc0, self.periods = initial_soc, periods

    def correct(self, plan: dict | None) -> bool:
        return plan is not None and plan["feasible"] and plan["objective"] <= self.opt + TOL

    def labels(self, plan: dict | None) -> tuple[list[str], list[str]]:
        """(true, predicted) hourly decisions. If the plan is one of several tied optima, it is the truth."""
        pred = None if plan is None else plan["path"]
        truth = pred if pred in self.optimal_paths else self.optimal_paths[0]
        return (battery_actions(truth, self.soc0, self.periods),
                battery_actions(pred, self.soc0, self.periods))

    def row(self, method: str, top1: dict | None, best: dict | None, time_s: float | None,
            stats: dict | None = None, reps: int | None = None, ar: float | None = None) -> dict:
        p_opt = stats["p_optimal"] if stats else (1.0 if self.correct(top1) else 0.0)
        t_true, t_pred = self.labels(top1)
        b_true, b_pred = self.labels(best)
        return {
            "instance": self.index, "seed": self.seed, "tier": self.tier, "method": method, "reps": reps,
            "correct_top1": self.correct(top1),
            "correct_best": self.correct(best),
            "labels_top1": {"true": t_true, "pred": t_pred},
            "labels_best": {"true": b_true, "pred": b_pred},
            "top1_plan": top1, "best_plan": best,
            "p_optimal": p_opt,
            "approximation_ratio": stats["approximation_ratio"] if stats else ar,
            "p_valid": stats["p_valid"] if stats else None,
            "p_feasible": stats["p_feasible"] if stats else None,
            "best_gap": None if best is None else best["objective"] - self.opt,
            "samples_99": samples_99(p_opt) if stats else None,
            "time_s": time_s,
        }

    def ar_of(self, objective: float) -> float:
        return 1.0 if self.worst - self.opt <= TOL else (self.worst - objective) / (self.worst - self.opt)


def run_instance(index: int, seed: int, tier: str, shots: int, qaoa: bool, noisy: bool,
                 max_reps: int, lp=None, no_battery=None, log=print) -> list[dict]:
    sc = random_scenario(seed)
    soc0, T = sc.battery.initial_soc, len(sc.periods)
    exact = solve_exact(sc, TIERS[tier], tier)
    ctx = _Ctx(index, seed, tier, exact, soc0, T)
    best = _plan(exact.details["best_path"], ctx.opt)
    rows = [{**ctx.row("exact", best, best, exact.provenance.solve_time_s, ar=1.0),
             "n_paths": exact.details["n_paths"], "n_optimal_paths": len(ctx.optimal_paths)}]

    # classical references with a single deterministic answer
    lp = lp or solve_lp(sc)
    lp_plan = _plan(lp.evaluation.soc_trajectory, lp.evaluation.objective)  # continuous: may beat the levels
    rows.append(ctx.row("lp", lp_plan, lp_plan, lp.provenance.solve_time_s))
    nb = no_battery or solve_no_battery(sc)
    nb_plan = _plan([soc0] * T, nb.evaluation.objective)
    rows.append(ctx.row("no_battery", nb_plan, nb_plan, nb.provenance.solve_time_s,
                        ar=ctx.ar_of(nb.evaluation.objective)))

    sa = solve_annealing(sc, tier, reads=shots, seed=seed)
    sa_stats = sa.details["qaoa_sampled"]
    rows.append(ctx.row("annealing", _from_top(sa_stats), _best(sa.details["best_found"]),
                        sa.provenance.solve_time_s, stats=sa_stats))

    # uniform random guessing: analytic success rate; answers from an actual sample of `shots` bitstrings
    model = build_qubo(sc, tier)
    table = decoder.path_table(sc, model)
    n = model.num_qubits
    sampled = np.bincount(np.random.default_rng(seed).integers(0, 2 ** n, shots), minlength=2 ** n) / shots
    found = decoder.best_found(sampled, table)
    stats = decoder.distribution_stats(np.full(2 ** n, 1 / 2 ** n), table)
    rows.append(ctx.row("random", _from_top(decoder.distribution_stats(sampled, table)),
                        None if found is None else _plan(found.path, found.objective), 0.0, stats=stats))

    if qaoa:
        start = time.perf_counter()
        ideal = run_depth_sweep(sc, tier, max_reps=max_reps, shots=shots)
        log(f"    {tier} QAOA ideal p=1..{max_reps} trained in {time.perf_counter() - start:.1f} s")
        for r in ideal:
            d = r.details
            # ideal: top-1 from exact probabilities; best-of-N from the actual shots
            rows.append(ctx.row("qaoa_ideal", _from_top(d["qaoa_exact"]), _best(d["best_found"]),
                                d["training"]["seconds"], stats=d["qaoa_exact"], reps=d["reps"]))
            if noisy:
                start = time.perf_counter()
                nz = run_noisy_simulation(sc, r).details
                rows.append(ctx.row("qaoa_noisy", _from_top(nz["qaoa_sampled"]), _best(nz["best_found"]),
                                    time.perf_counter() - start, stats=nz["qaoa_sampled"], reps=d["reps"]))
    return rows


def _best(found: dict | None) -> dict | None:
    return None if found is None else _plan(found["path"], found["objective"])


def macro_f1(y_true: list[str], y_pred: list[str]) -> float:
    """Macro-averaged F1 over the decision classes that occur (a missing plan, 'none', is always wrong)."""
    classes = (set(y_true) | set(y_pred)) - {"none"}
    scores = []
    for c in sorted(classes):
        tp = sum(t == c and p == c for t, p in zip(y_true, y_pred))
        fp = sum(t != c and p == c for t, p in zip(y_true, y_pred))
        fn = sum(t == c and p != c for t, p in zip(y_true, y_pred))
        scores.append(2 * tp / (2 * tp + fp + fn) if tp + fp + fn else 1.0)
    return statistics.fmean(scores) if scores else 0.0


def run_suite(instances: int = 20, tiers: tuple[str, ...] = ("Q3", "Q9", "Q18"),
              qaoa_instances: dict[str, int] | None = None, noisy_tiers: tuple[str, ...] = ("Q3", "Q9"),
              shots: int = 4096, max_reps: int = 3, first_seed: int = 1000, log=print) -> dict:
    """qaoa_instances: per tier, how many of the instances also get QAOA (default: all, Q18: 3)."""
    qaoa_instances = qaoa_instances or {"Q18": 3}
    started = time.perf_counter()
    instance_info, rows = [], []
    for i in range(instances):
        seed = first_seed + i
        sc = random_scenario(seed)
        lp, nb = solve_lp(sc), solve_no_battery(sc)
        instance_info.append({"instance": i, "seed": seed,
                              "periods": [p.model_dump() for p in sc.periods],
                              "lp_objective": lp.evaluation.objective, "lp_time_s": lp.provenance.solve_time_s,
                              "no_battery_objective": nb.evaluation.objective})
        log(f"[{i + 1}/{instances}] seed {seed}  LP ${lp.evaluation.objective:,.0f}")
        for tier in tiers:
            q = i < qaoa_instances.get(tier, instances)
            rows += run_instance(i, seed, tier, shots, qaoa=q, noisy=q and tier in noisy_tiers,
                                 max_reps=max_reps, lp=lp, no_battery=nb, log=log)
    result = {
        "created_at": utc_now(),
        "config": {"instances": instances, "tiers": list(tiers), "qaoa_instances": qaoa_instances,
                   "noisy_tiers": list(noisy_tiers), "shots": shots, "max_reps": max_reps,
                   "first_seed": first_seed, "noise_backend": "FakeFez",
                   "annealing": "100 sweeps, geometric schedule, reads = shots"},
        "library_versions": library_versions(*PACKAGES),
        "wall_time_s": time.perf_counter() - started,
        "instances": instance_info,
        "rows": rows,
        "summary": summarize(rows),
    }
    result["headline"] = headline(result)
    return result


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["tier"], r["method"], r["reps"])].append(r)

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return statistics.fmean(xs) if xs else None

    def median(xs):
        xs = [x for x in xs if x is not None]
        return statistics.median(xs) if xs else None

    def f1(g, which):
        y_true = [lab for r in g for lab in r[which]["true"]]
        y_pred = [lab for r in g for lab in r[which]["pred"]]
        return macro_f1(y_true, y_pred)

    out = []
    for (tier, method, reps), g in sorted(groups.items(),
                                          key=lambda kv: (kv[0][0], METHOD_ORDER[kv[0][1]], kv[0][2] or 0)):
        out.append({
            "tier": tier, "method": method, "reps": reps, "instances": len(g),
            "accuracy_top1": mean([1.0 if r["correct_top1"] else 0.0 for r in g]),
            "accuracy_best": mean([1.0 if r["correct_best"] else 0.0 for r in g]),
            "f1_top1": f1(g, "labels_top1"),
            "f1_best": f1(g, "labels_best"),
            "p_optimal_mean": mean([r["p_optimal"] for r in g]),
            "p_optimal_min": min(r["p_optimal"] for r in g),
            "approximation_ratio_mean": mean([r["approximation_ratio"] for r in g]),
            "p_valid_mean": mean([r["p_valid"] for r in g]),
            "best_gap_mean": mean([r["best_gap"] for r in g]),
            "samples_99_median": median([r["samples_99"] for r in g]),
            "time_s_mean": mean([r["time_s"] for r in g]),
        })
    return out


METHOD_ORDER = {"exact": 0, "lp": 1, "annealing": 2, "no_battery": 3, "random": 4, "qaoa_ideal": 5, "qaoa_noisy": 6}
METHOD_LABEL = {"exact": "Exact enumeration (classical)", "lp": "Linear program, CBC (classical)",
                "annealing": "Simulated annealing (classical)", "no_battery": "No battery (classical baseline)",
                "random": "Uniform random sampling", "qaoa_ideal": "QAOA, ideal simulator",
                "qaoa_noisy": "QAOA, IBM noise model (FakeFez)"}
SAMPLING = {"annealing", "random", "qaoa_ideal", "qaoa_noisy"}


def headline(result: dict) -> list[dict]:
    """One row per tier: accuracy (best-of-N) / F1 for the main methods, deepest QAOA only."""
    max_p = result["config"]["max_reps"]
    rows = []
    for tier in result["config"]["tiers"]:
        cell = {}
        for s in result["summary"]:
            if s["tier"] != tier or (s["method"].startswith("qaoa") and s["reps"] != max_p):
                continue
            cell[s["method"]] = {"accuracy_top1": s["accuracy_top1"], "accuracy_best": s["accuracy_best"],
                                 "f1_best": s["f1_best"], "f1_top1": s["f1_top1"], "instances": s["instances"]}
        rows.append({"tier": tier, "methods": cell})
    return rows


def to_markdown(result: dict) -> str:
    cfg = result["config"]

    def f(v, fmt):
        if v is None:
            return "—"
        if isinstance(v, float) and math.isinf(v):
            return "∞"
        return format(v, fmt)

    max_p = cfg["max_reps"]
    lines = [
        "# Benchmark results: QAOA vs classical algorithms",
        "",
        f"Generated {result['created_at']} · {cfg['instances']} random grid instances (seeds {cfg['first_seed']}–"
        f"{cfg['first_seed'] + cfg['instances'] - 1}) · {cfg['shots']} samples per sampling method · "
        f"QAOA on {', '.join(f'{t}: {n}' for t, n in cfg['qaoa_instances'].items())} instances (others: all) · "
        f"wall time {result['wall_time_s'] / 60:.1f} min",
        "",
        "## Metric definitions",
        "",
        "- **Accuracy (top-1)**: share of instances where the method's single most likely valid plan is optimal.",
        "- **Accuracy (best-of-N)**: share of instances where the best of its N samples is optimal "
        "(what the system reports).",
        "- **F1 (macro)**: each hour's battery decision (charge / idle / discharge) is a predicted label, compared "
        "with the optimal plan's decision; macro-averaged F1 over all instances and hours. A missing plan counts "
        "as wrong.",
        "- **Success rate**: probability that ONE sample is optimal (QAOA ideal: exact statevector probability; "
        "random: analytic; annealing and noisy QAOA: measured).",
        "- **AR**: approximation ratio, 1 = optimal, 0 = worst feasible plan; invalid samples count as the worst.",
        "- **Samples for 99%**: samples needed to hit the optimum at least once with 99% confidence.",
        "- **Time**: wall-clock seconds on this laptop. QAOA time is the classical SIMULATION of training, "
        "not QPU time, and is not a quantum speed measurement.",
        "",
        f"## Headline (QAOA at p = {max_p}): accuracy best-of-N / top-1 · F1 best-of-N",
        "",
        "| Tier | Exact | LP | Simulated annealing | No battery | Random sampling | QAOA ideal | QAOA noisy |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for h in headline(result):
        cells = []
        for m in ("exact", "lp", "annealing", "no_battery", "random", "qaoa_ideal", "qaoa_noisy"):
            c = h["methods"].get(m)
            cells.append("—" if c is None else
                         f"{c['accuracy_best']:.0%} / {c['accuracy_top1']:.0%} · F1 {c['f1_best']:.2f}")
        lines.append(f"| {h['tier']} | " + " | ".join(cells) + " |")
    lines.append("")

    for tier in cfg["tiers"]:
        lines += [f"## {tier}: full table", "",
                  "| Method | p | Instances | Accuracy top-1 | Accuracy best-of-N | F1 top-1 | F1 best-of-N | "
                  "Success rate | AR | Valid samples | Best gap $ | Samples for 99% | Time s |",
                  "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for s in (s for s in result["summary"] if s["tier"] == tier):
            sampling = s["method"] in SAMPLING
            lines.append(
                f"| {METHOD_LABEL[s['method']]} | {s['reps'] or ''} | {s['instances']} | "
                f"{f(s['accuracy_top1'], '.0%')} | {f(s['accuracy_best'], '.0%')} | "
                f"{f(s['f1_top1'], '.3f')} | {f(s['f1_best'], '.3f')} | "
                f"{f(s['p_optimal_mean'], '.2%') if sampling else '—'} | {f(s['approximation_ratio_mean'], '.3f')} | "
                f"{f(s['p_valid_mean'], '.1%')} | {f(s['best_gap_mean'], ',.0f')} | "
                f"{f(s['samples_99_median'], ',.0f')} | {f(s['time_s_mean'], '.3f')} |")
        lines.append("")
    lp = [i["lp_objective"] for i in result["instances"]]
    lines += [f"LP (continuous optimum) solved all {len(lp)} instances; mean time "
              f"{statistics.fmean(i['lp_time_s'] for i in result['instances']) * 1000:.0f} ms.", ""]
    return "\n".join(lines)


def _finite(obj):
    if isinstance(obj, float) and math.isinf(obj):
        return None
    if isinstance(obj, dict):
        return {k: _finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_finite(v) for v in obj]
    return obj


def save(result: dict, directory: Path = RESULTS_DIR) -> dict[str, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = result["created_at"].replace(":", "").replace("+0000", "Z")
    paths = {"json": directory / f"benchmark_{stamp}.json", "latest_json": directory / "latest.json",
             "latest_md": directory / "latest.md"}
    text = json.dumps(_finite(result), indent=2)  # infinite samples_99 ("never") -> null
    paths["json"].write_text(text, encoding="utf-8")
    paths["latest_json"].write_text(text, encoding="utf-8")
    paths["latest_md"].write_text(to_markdown(result), encoding="utf-8")
    return paths
