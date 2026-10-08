# Benchmark results: QAOA vs classical algorithms

Generated 2026-10-08T10:58:39+00:00 · 20 random grid instances (seeds 1000–1019) · 4096 samples per sampling method · QAOA on Q18: 3 instances (others: all) · wall time 28.7 min

## Metric definitions

- **Accuracy (top-1)**: share of instances where the method's single most likely valid plan is optimal.
- **Accuracy (best-of-N)**: share of instances where the best of its N samples is optimal (what the system reports).
- **F1 (macro)**: each hour's battery decision (charge / idle / discharge) is a predicted label, compared with the optimal plan's decision; macro-averaged F1 over all instances and hours. A missing plan counts as wrong.
- **Success rate**: probability that ONE sample is optimal (QAOA ideal: exact statevector probability; random: analytic; annealing and noisy QAOA: measured).
- **AR**: approximation ratio, 1 = optimal, 0 = worst feasible plan; invalid samples count as the worst.
- **Samples for 99%**: samples needed to hit the optimum at least once with 99% confidence.
- **Time**: wall-clock seconds on this laptop. QAOA time is the classical SIMULATION of training, not QPU time, and is not a quantum speed measurement.

## Headline (QAOA at p = 3): accuracy best-of-N / top-1 · F1 best-of-N

| Tier | Exact | LP | Simulated annealing | No battery | Random sampling | QAOA ideal | QAOA noisy |
|---|---|---|---|---|---|---|---|
| Q3 | 100% / 100% · F1 1.00 | 100% / 100% · F1 0.91 | 100% / 100% · F1 1.00 | 25% / 25% · F1 0.22 | 100% / 15% · F1 1.00 | 100% / 85% · F1 1.00 | 100% / 85% · F1 1.00 |
| Q9 | 100% / 100% · F1 1.00 | 100% / 100% · F1 0.94 | 100% / 50% · F1 1.00 | 25% / 25% · F1 0.21 | 100% / 0% · F1 1.00 | 100% / 0% · F1 1.00 | 100% / 30% · F1 1.00 |
| Q18 | 100% / 100% · F1 1.00 | 100% / 100% · F1 0.95 | 100% / 0% · F1 1.00 | 25% / 25% · F1 0.21 | 10% / 5% · F1 0.40 | 100% / 0% · F1 1.00 | — |

## Q3: full table

| Method | p | Instances | Accuracy top-1 | Accuracy best-of-N | F1 top-1 | F1 best-of-N | Success rate | AR | Valid samples | Best gap $ | Samples for 99% | Time s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Exact enumeration (classical) |  | 20 | 100% | 100% | 1.000 | 1.000 | — | 1.000 | — | 0 | — | 0.000 |
| Linear program, CBC (classical) |  | 20 | 100% | 100% | 0.905 | 0.905 | — | — | — | -1,316 | — | 0.050 |
| Simulated annealing (classical) |  | 20 | 100% | 100% | 1.000 | 1.000 | 100.00% | 1.000 | 100.0% | 0 | 1 | 0.024 |
| No battery (classical baseline) |  | 20 | 25% | 25% | 0.222 | 0.222 | — | 0.735 | — | 6,401 | — | 0.000 |
| Uniform random sampling |  | 20 | 15% | 100% | 0.330 | 1.000 | 15.00% | 0.556 | 100.0% | 0 | 35 | 0.000 |
| QAOA, ideal simulator | 1 | 20 | 80% | 100% | 0.870 | 1.000 | 69.53% | 0.972 | 100.0% | 0 | 3 | 0.370 |
| QAOA, ideal simulator | 2 | 20 | 95% | 100% | 0.967 | 1.000 | 75.94% | 0.990 | 100.0% | 0 | 2 | 2.603 |
| QAOA, ideal simulator | 3 | 20 | 85% | 100% | 0.902 | 1.000 | 81.62% | 0.994 | 100.0% | 0 | 2 | 3.435 |
| QAOA, IBM noise model (FakeFez) | 1 | 20 | 80% | 100% | 0.870 | 1.000 | 68.02% | 0.964 | 100.0% | 0 | 4 | 4.635 |
| QAOA, IBM noise model (FakeFez) | 2 | 20 | 95% | 100% | 0.967 | 1.000 | 73.19% | 0.976 | 100.0% | 0 | 2 | 4.958 |
| QAOA, IBM noise model (FakeFez) | 3 | 20 | 85% | 100% | 0.902 | 1.000 | 77.47% | 0.974 | 100.0% | 0 | 2 | 5.301 |

## Q9: full table

| Method | p | Instances | Accuracy top-1 | Accuracy best-of-N | F1 top-1 | F1 best-of-N | Success rate | AR | Valid samples | Best gap $ | Samples for 99% | Time s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Exact enumeration (classical) |  | 20 | 100% | 100% | 1.000 | 1.000 | — | 1.000 | — | 0 | — | 0.001 |
| Linear program, CBC (classical) |  | 20 | 100% | 100% | 0.938 | 0.938 | — | — | — | -1,296 | — | 0.050 |
| Simulated annealing (classical) |  | 20 | 50% | 100% | 0.762 | 1.000 | 12.42% | 0.577 | 100.0% | 0 | 39 | 0.115 |
| No battery (classical baseline) |  | 20 | 25% | 25% | 0.212 | 0.212 | — | 0.739 | — | 6,421 | — | 0.000 |
| Uniform random sampling |  | 20 | 0% | 100% | 0.331 | 1.000 | 0.21% | 0.012 | 5.3% | 0 | 2,356 | 0.000 |
| QAOA, ideal simulator | 1 | 20 | 15% | 100% | 0.526 | 1.000 | 1.67% | 0.090 | 28.8% | 0 | 298 | 1.070 |
| QAOA, ideal simulator | 2 | 20 | 20% | 100% | 0.517 | 1.000 | 2.66% | 0.138 | 34.0% | 0 | 183 | 8.328 |
| QAOA, ideal simulator | 3 | 20 | 0% | 100% | 0.190 | 1.000 | 4.85% | 0.262 | 59.5% | 0 | 97 | 10.231 |
| QAOA, IBM noise model (FakeFez) | 1 | 20 | 5% | 100% | 0.516 | 1.000 | 1.30% | 0.073 | 24.5% | 0 | 388 | 5.152 |
| QAOA, IBM noise model (FakeFez) | 2 | 20 | 30% | 100% | 0.573 | 1.000 | 1.84% | 0.095 | 26.7% | 0 | 281 | 5.372 |
| QAOA, IBM noise model (FakeFez) | 3 | 20 | 30% | 100% | 0.584 | 1.000 | 2.58% | 0.131 | 35.0% | 0 | 174 | 5.361 |

## Q18: full table

| Method | p | Instances | Accuracy top-1 | Accuracy best-of-N | F1 top-1 | F1 best-of-N | Success rate | AR | Valid samples | Best gap $ | Samples for 99% | Time s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Exact enumeration (classical) |  | 20 | 100% | 100% | 1.000 | 1.000 | — | 1.000 | — | 0 | — | 0.007 |
| Linear program, CBC (classical) |  | 20 | 100% | 100% | 0.954 | 0.954 | — | — | — | -10 | — | 0.050 |
| Simulated annealing (classical) |  | 20 | 0% | 100% | 0.539 | 1.000 | 1.52% | 0.680 | 100.0% | 0 | 376 | 0.241 |
| No battery (classical baseline) |  | 20 | 25% | 25% | 0.207 | 0.207 | — | 0.795 | — | 7,707 | — | 0.000 |
| Uniform random sampling |  | 20 | 5% | 10% | 0.307 | 0.403 | 0.00% | 0.000 | 0.1% | 8,272 | 1,207,216 | 0.000 |
| QAOA, ideal simulator | 1 | 3 | 0% | 100% | 0.556 | 1.000 | 0.09% | 0.053 | 16.1% | 0 | 5,033 | 16.613 |
| QAOA, ideal simulator | 2 | 3 | 0% | 100% | 0.600 | 1.000 | 0.15% | 0.084 | 21.4% | 0 | 3,077 | 71.305 |
| QAOA, ideal simulator | 3 | 3 | 0% | 100% | 0.600 | 1.000 | 0.23% | 0.138 | 32.0% | 0 | 1,848 | 91.083 |

LP (continuous optimum) solved all 20 instances; mean time 50 ms.
