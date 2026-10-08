import json
import math

import pytest

from app.benchmark.suite import (
    battery_actions,
    macro_f1,
    random_scenario,
    run_suite,
    samples_99,
    save,
    to_markdown,
)


def test_random_scenarios_are_reproducible_and_valid():
    a, b = random_scenario(1001), random_scenario(1001)
    assert a == b
    assert a != random_scenario(1002)
    for p in a.periods:
        assert p.demand % 5 == 0 and p.solar % 5 == 0 and p.wind % 5 == 0
    assert a.battery.capacity == 50  # all tiers (levels up to 50) stay valid


def test_samples_99():
    assert samples_99(1.0) == 1
    assert samples_99(0.0) == math.inf
    assert samples_99(0.5) == 7  # 0.5^7 = 0.8% failure <= 1%, 0.5^6 = 1.6% is not enough
    assert samples_99(0.99) == 1


def test_battery_actions():
    assert battery_actions([0, 20, 0], 0, 3) == ["idle", "charge", "discharge"]
    assert battery_actions([10, 10, 30], 0, 3) == ["charge", "idle", "charge"]
    assert battery_actions(None, 0, 3) == ["none", "none", "none"]


def test_macro_f1_by_hand():
    assert macro_f1(["idle", "charge"], ["idle", "charge"]) == 1.0
    # truth: c c i d ; pred: c i i d -> charge P=1 R=.5 F1=2/3 ; idle P=.5 R=1 F1=2/3 ; discharge F1=1
    assert macro_f1(["charge", "charge", "idle", "discharge"],
                    ["charge", "idle", "idle", "discharge"]) == pytest.approx((2 / 3 + 2 / 3 + 1) / 3)
    # a missing plan ('none') is simply wrong: idle recall 0 -> F1 0
    assert macro_f1(["idle", "idle"], ["none", "none"]) == 0.0


@pytest.fixture(scope="module")
def small_suite():
    return run_suite(instances=2, tiers=("Q3", "Q9"), qaoa_instances={"Q9": 1}, noisy_tiers=("Q3",),
                     shots=512, max_reps=1, log=lambda *_: None)


def test_suite_rows(small_suite):
    rows = small_suite["rows"]
    methods = {(r["tier"], r["method"]) for r in rows}
    all_methods = ("exact", "lp", "no_battery", "annealing", "random", "qaoa_ideal", "qaoa_noisy")
    assert {("Q3", m) for m in all_methods} <= methods
    q9_qaoa = [r for r in rows if r["tier"] == "Q9" and r["method"] == "qaoa_ideal"]
    assert [r["instance"] for r in q9_qaoa] == [0]  # QAOA only on the first Q9 instance
    assert all(r["method"] != "qaoa_noisy" for r in rows if r["tier"] == "Q9")
    for tier in ("Q3", "Q9"):  # every instance has the classical methods for every tier
        for m in ("exact", "lp", "no_battery", "annealing", "random"):
            assert sorted(r["instance"] for r in rows if r["tier"] == tier and r["method"] == m) == [0, 1]
    for r in rows:
        assert 0 <= r["p_optimal"] <= 1
        assert len(r["labels_best"]["true"]) == len(r["labels_best"]["pred"]) == 3
        if r["best_gap"] is not None and r["method"] != "lp":
            assert r["best_gap"] >= -1e-6  # no discrete method beats the exact optimum
        if r["method"] == "lp":
            assert r["best_gap"] <= 1e-6 and r["correct_best"]  # continuous LP is never worse


def test_exact_is_perfect(small_suite):
    for r in small_suite["rows"]:
        if r["method"] == "exact":
            assert r["correct_top1"] and r["correct_best"]
            assert r["labels_best"]["true"] == r["labels_best"]["pred"]


def test_summary_headline_markdown(small_suite, tmp_path):
    s = {(x["tier"], x["method"], x["reps"]): x for x in small_suite["summary"]}
    assert s[("Q3", "exact", None)]["accuracy_best"] == 1.0
    assert s[("Q3", "exact", None)]["f1_best"] == 1.0
    assert s[("Q9", "qaoa_ideal", 1)]["instances"] == 1
    for x in small_suite["summary"]:
        assert 0 <= x["accuracy_top1"] <= 1 and 0 <= x["f1_best"] <= 1
    head = {h["tier"]: h["methods"] for h in small_suite["headline"]}
    assert set(head["Q3"]) == {"exact", "lp", "no_battery", "annealing", "random", "qaoa_ideal", "qaoa_noisy"}
    md = to_markdown(small_suite)
    for text in ("## Headline", "Accuracy (top-1)", "F1 (macro)", "Simulated annealing (classical)",
                 "No battery (classical baseline)", "not QPU time"):
        assert text in md
    paths = save(small_suite, tmp_path)
    data = json.loads(paths["latest_json"].read_text(encoding="utf-8"))  # valid JSON (no Infinity)
    assert len(data["rows"]) == len(small_suite["rows"])
    assert paths["latest_md"].read_text(encoding="utf-8") == md
