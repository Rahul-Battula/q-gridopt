# Grover adaptive search: query counts vs classical search

Generated 2026-10-08T18:08:15+00:00 · 200 independent runs per row · seed 1234 · preset scenario_b · one query = one evaluation of the cost function.

**What this shows.** Grover's algorithm needs about sqrt(N) queries where a classical unstructured search needs about N/2. The speedup is real and provable, but it is a speedup over *unstructured search of the qubit bitstring space*. A classical method that exploits the structure of the battery problem (try only valid plans, or dynamic programming) needs far fewer queries, so **no advantage over the best classical solver is claimed**. It also needs a fault-tolerant machine to run at useful sizes.

## The three project tiers

| Tier | Qubits | Bitstrings N | Valid plans | Grover (queries) | Blind search of N | Speedup vs blind | Structured classical | Speedup vs structured | Success | Oracle+diffuser on FakeFez (2q gates) |
|---|---|---|---|---|---|---|---|---|---|---|
| Q3 | 3 | 8 | 8 | 6.2 | 4.3 | 0.69x | 4.7 | 0.75x | 100% | 14 |
| Q9 | 9 | 512 | 27 | 64.8 | 255.9 | 3.95x | 13.3 | 0.21x | 100% | 1368 |
| Q18 | 18 | 262,144 | 216 | 1,379.4 | 132,824.3 | 96.29x | 104.1 | 0.08x | 100% | not run |

## Scaling: Q3 encoding, grids with more hours (random hours, seed 11)

Every bitstring is a valid plan here, so blind search and enumeration are the same classical baseline.

| Hours = qubits | N = 2^n | Optimal plans | Grover (queries) | Blind search | Speedup | Success |
|---|---|---|---|---|---|---|
| 3 | 8 | 1 | 5.8 | 4.6 | 0.79x | 100% |
| 4 | 16 | 1 | 8.1 | 8.5 | 1.04x | 100% |
| 5 | 32 | 2 | 9.1 | 10.4 | 1.14x | 100% |
| 6 | 64 | 2 | 12.5 | 21.5 | 1.72x | 100% |
| 7 | 128 | 2 | 20.1 | 42.2 | 2.10x | 100% |
| 8 | 256 | 2 | 29.2 | 82.6 | 2.82x | 100% |
| 9 | 512 | 2 | 41.9 | 175.5 | 4.19x | 100% |
| 10 | 1,024 | 2 | 62.7 | 361.0 | 5.76x | 100% |
| 11 | 2,048 | 2 | 78.8 | 671.8 | 8.52x | 100% |
| 12 | 4,096 | 4 | 79.5 | 888.6 | 11.17x | 100% |
| 13 | 8,192 | 6 | 103.0 | 1,183.4 | 11.49x | 100% |
| 14 | 16,384 | 8 | 129.1 | 1,728.4 | 13.39x | 100% |
| 15 | 32,768 | 8 | 171.9 | 3,711.0 | 21.58x | 100% |

Fitted scaling, queries ~ N^x: Grover x = 0.42, blind classical x = 0.82 (theory: 0.5 and 1.0). Grover first needs fewer queries than blind search at 4 hours.

## Honest caveats

- The fitted slopes sit below 0.5 / 1.0 partly because the number of tied optimal plans grows with the grid, which makes every search easier; read the speedup column, not the slopes, as the evidence.
- Below the break-even size, unknown-M Grover search is *slower* than just trying bitstrings (its constant factor is large).
- The battery problem is a chain: classical dynamic programming solves it in polynomial time (see scaling.md), which beats any search, quantum or classical.
- An oracle call here is one coherent cost evaluation. Building that oracle as a real reversible circuit, and running it error-corrected, is what a hardware advantage would require; on today's chips the oracle alone costs far more gates than can run before noise dominates (last column).
- The statevector evolution is exact (closed form, verified against the Qiskit circuit in tests); no quantum computer produced these query counts.
