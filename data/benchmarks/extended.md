# Extended model study (unit commitment, forecast uncertainty, reserve)

Generated 2026-10-08T16:32:51+00:00. Costs in $ (expected value when the scenario has forecast cases).

## A. What each feature changes

| Model | Tier | No battery (greedy) | Exact optimum | MILP (continuous battery) | Best battery plan | Gas unit | Start-ups | Worst case |
|---|---|---|---|---|---|---|---|---|
| Scenario B (base model) | Q3 | 10,925 | 9,175 | 9,175 | [0, 20, 0] | - | 0 | - |
| + unit commitment | Q3U | 13,450 | 11,700 | 10,825 | [0, 20, 0] | on off on | 2 | - |
| + forecast uncertainty | Q3U | 22,632 | 14,694 | 14,096 | [0, 20, 0] | on on on | 1 | 15,255 |
| + reserve margin (Scenario C) | Q3U | 23,892 | 14,784 | 14,096 | [0, 20, 0] | on on on | 1 | 15,555 |

## B. QAOA vs classical on Scenario C

| Tier | Qubits | p | P(valid) | QAOA P(optimal) | Random P(optimal) | Annealing P(optimal) | Noisy sim P(optimal) | Approx. ratio | 2q gates (chip) | Best plan found |
|---|---|---|---|---|---|---|---|---|---|---|
| Q3U | 12 | 1 | 23.5% | 0.41% | 0.0244% | 3.32% | 0.20% | 0.136 | 179 | [0, 20, 0] gas on on on $14,784 |
| Q3U | 12 | 2 | 41.2% | 0.86% | 0.0244% | 3.32% | 0.37% | 0.255 | 394 | [0, 20, 0] gas on on on $14,784 |
| Q3U | 12 | 3 | 90.3% | 1.97% | 0.0244% | 3.32% | 0.71% | 0.567 | 639 | [0, 20, 0] gas on on on $14,784 |
| Q9U | 18 | 1 | 15.7% | 0.11% | 0.0004% | 1.83% | - | 0.053 | 396 | [0, 20, 0] gas on on on $14,784 |
| Q9U | 18 | 2 | 20.1% | 0.19% | 0.0004% | 1.83% | - | 0.086 | 1056 | [0, 20, 0] gas on on on $14,784 |
| Q9U | 18 | 3 | 22.6% | 0.24% | 0.0004% | 1.83% | - | 0.107 | 1557 | [0, 20, 0] gas on on on $14,784 |
