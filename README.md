# Q-GridOpt

**Battery scheduling for a small renewable-energy grid, solved with QAOA on Qiskit simulators and a real IBM Quantum computer, and benchmarked honestly against classical solvers.**

> **Claim:** We formulate renewable-energy scheduling with battery storage as a QUBO, solve it with QAOA on simulators and IBM Quantum hardware, and benchmark it against exact classical solvers.
> **Not claimed:** quantum advantage or speedup. At this size a classical computer solves every instance exactly in milliseconds. See [Quantum advantage: the honest answer](#4-quantum-advantage-the-honest-answer).

---

See also: [architecture diagram](docs/architecture.md) and [pitch material](docs/pitch.md).

## The problem

A grid has solar, wind, a gas plant and a battery over 3 periods (morning, afternoon, evening). Surplus afternoon solar can be stored and used in the expensive evening peak, replacing gas. The question is **when to charge and discharge the battery** so that cost and CO2 are minimal.

Default "Scenario B" (1 period = 1 hour, so MW = MWh):

| Period | Demand | Solar | Wind |
|---|---|---|---|
| Morning | 80 | 30 | 20 |
| Afternoon | 120 | 120 | 20 |
| Evening | 150 | 10 | 40 |

Gas max 100 MW; battery 50 MWh, 30 MW max rate. Optimal plan: charge 20 MWh in the afternoon, discharge it in the evening. **$9,175, 49.5 t CO2, no curtailment**, versus $10,925 with no battery (hand-verified in [docs/manual_verification.md](docs/manual_verification.md)).

## How it works

1. **Battery plan -> QUBO.** One yes/no variable per (hour, battery level). Energy = the dollar cost of the plan (from a merit-order dispatch: renewables first, then gas) plus a penalty for invalid plans.
2. **QUBO -> Ising Hamiltonian** (`SparsePauliOp`).
3. **QAOA circuit** (`qaoa_ansatz`, depth p = 1..3). Angles are trained on a simulator (COBYLA).
4. **Sample** on the Aer simulator (ideal), on Aer with an IBM chip noise model (FakeFez), and on a **real IBM QPU**.
5. **Decode** bitstrings back to a battery path -> schedule -> score it with the **same evaluator** used for every classical solver.

QAOA decides the battery trajectory; the merit-order rule fills in solar, wind and gas for each hour. This is stated openly, not hidden.

Three problem sizes:

| Tier | Qubits | Battery levels (MWh) | Role |
|---|---|---|---|
| Q3 | 3 | {0, 20} | real hardware target |
| Q9 | 9 | {0, 20, 40}, one-hot | main simulator result |
| Q18 | 18 | 0..50 step 10, one-hot | simulator stress test |

Correctness check: for every bitstring, the QUBO energy equals the evaluator's cost (plus the penalty for rule-breaking plans), and the QUBO ground state is the exact optimum, for all tiers and both presets.

### Extended model: unit commitment, forecast uncertainty, reserve margin

Three optional scenario features (all off in Scenarios A and B; all on in **Scenario C**). They are part of the shared evaluator, the QUBO, the exact solver, the MILP and the dashboard.

| Feature | What it adds | How it enters the QUBO |
|---|---|---|
| **Unit commitment** | The gas plant must be switched **on** to produce, runs at least 40 MW while on, and costs $800 per start-up | Per-hour state = (battery level, gas on/off), one-hot: tiers **Q3U** (12 qubits) and **Q9U** (18 qubits). Start-up cost only couples two consecutive hours, so the energy stays quadratic. |
| **Forecast uncertainty** | Three weather cases (30% cloudy and calm, 50% as forecast, 20% sunny and windy). Battery plan and gas on/off are decided *before* the weather is known; dispatch reacts. Cost = expected value | Each hour's cost is the probability-weighted average over cases |
| **Reserve margin** | Spare capacity (unused gas of an *on* unit + battery discharge headroom) must cover 10% of demand; $50 per missing MW | A shortfall penalty in each hour's cost |

The correctness test is the same one as before, now with all three on: for every plan the QUBO energy equals the evaluator's objective, and the QUBO's ground state is the exact optimum (`backend/tests/test_extended.py`). The classical LP becomes a two-stage stochastic **mixed-integer program** (CBC) for these scenarios, and its objective matches the evaluator to 1e-4.

**What each feature changes** (`python backend\scripts\run_extended.py`, [data/benchmarks/extended.md](data/benchmarks/extended.md)). Exact = best discrete plan, MILP = continuous battery, "no battery" = greedy dispatch:

| Model | No battery | Exact optimum | MILP | Best battery plan | Gas unit on/off | Start-ups |
|---|---|---|---|---|---|---|
| Scenario B | $10,925 | $9,175 | $9,175 | [0, 20, 0] | n/a | n/a |
| + unit commitment | $13,450 | $11,700 | $10,825 | [0, 20, 0] | on, off, on | 2 |
| + forecast uncertainty | $22,632 | $14,694 | $14,096 | [0, 20, 0] | on, on, on | 1 |
| + reserve (Scenario C) | $23,892 | $14,784 | $14,096 | [0, 20, 0] | on, on, on | 1 |

Two things the extra features make visible:

- A start-up cost turns the battery's saving into an on/off scheduling problem.
- Under uncertainty the best plan keeps the gas unit on through the afternoon. With the same battery plan, gas on/off/on costs $11,700 when the forecast is right (cheaper than on-all-day at $14,600), but with the three weather cases it costs $23,914 expected and $52,755 in the worst case (unserved demand when the cloudy case hits), against $14,694 expected and $15,255 worst case for on-all-day.

The greedy no-battery baseline derives its gas commitment from the forecast alone, so it is caught short in the cloudy case. Its $23,892 against the best plan's $14,784 therefore mixes the battery's value with the value of the commitment hedge; the table does not separate the two.

**QAOA on Scenario C** (simulator, p = 1 / 2 / 3; unit-commitment circuits are far too deep for today's hardware, so these tiers are simulator-only):

| Tier | Qubits | P(valid) | QAOA P(optimal) | Random P(optimal) | Simulated annealing P(optimal) | Noisy sim (FakeFez) | 2-qubit gates on chip |
|---|---|---|---|---|---|---|---|
| Q3U | 12 | 24 / 41 / 90% | 0.41 / 0.86 / 1.97% | 0.024% | 3.3% | 0.2 / 0.4 / 0.7% | 179 / 394 / 639 |
| Q9U | 18 | 16 / 20 / 23% | 0.11 / 0.19 / 0.24% | 0.0004% | 1.8% | not run | 396 / 1,056 / 1,557 |

QAOA's best sampled plan is the exact optimum ($14,784, gas on all day, battery 0 -> 20 -> 0) at every depth, and it beats random guessing by about 80x on Q3U and about 600x on Q9U per sample. **But simulated annealing on the same QUBO finds the optimum more often per sample than QAOA does**, and exact enumeration (64 and 216 paths) solves both tiers in milliseconds. Same conclusion as before: no quantum advantage.

### Mapping to the hackathon brief (Use Case 04: grid load balancing and unit commitment)

| Brief | What the project does | Status |
|---|---|---|
| Balance supply and demand on a high-renewable grid | Hourly balance of solar, wind, gas, battery and unserved demand, enforced and checked by one evaluator | done |
| Unit commitment | Gas unit on/off with minimum output and start-up cost, decided by QAOA (tiers Q3U / Q9U), exact enumeration and a MILP | done, simplified: no minimum up/down times, one unit |
| Dispatch | Merit-order dispatch fills in solar, wind and gas around the quantum-chosen battery and commitment: a **hybrid** quantum-classical method | done |
| Optimisation under uncertainty | Three weighted solar/wind forecast cases, expected cost, worst case reported; commitment and battery decided before the outcome | done, simplified: three hand-set cases, not a calibrated forecast model |
| Lower curtailment, cost and emissions | Cost, CO2 and curtailment reported for every result (Scenario B: $9,175 against $10,925 with no battery, no curtailment) | done |
| Improved grid stability | A reserve-margin requirement with a penalty, and the shortfall reported | done, simplified: a spare-capacity margin only, no frequency, inertia or network (power flow) model |
| Quantum computing, run on real hardware | QAOA on a real IBM QPU for the 3-qubit tier (Q3, 6 s of QPU time); the unit-commitment tiers are simulator-only | done / partial |
| Applies to DISCOMs, APTRANSCO, load dispatch | The model is a one-region, 3-hour, one-gas-unit abstraction of a day-ahead dispatch problem. Real systems have tens to hundreds of units and 24-96 periods; this is a method demonstration, not a deployable tool | scope note |

---

## Results (grading criteria)

### 1. Novelty

- Renewable-energy scheduling **with storage** encoded as a state-path QUBO: the battery state-of-charge trajectory is the quantum decision, with exact dollar costs on the couplings.
- One shared evaluator scores every solver (LP, exact, annealing, QAOA ideal/noisy/hardware), so comparisons are like for like.
- Every result carries provenance (source, backend, job id, shots, library versions). Results from a simulator can never be labelled hardware.

### 2. Level of Qiskit programming

See [Where Qiskit is used](#where-qiskit-is-used). Highlights: `qaoa_ansatz`, `SparsePauliOp`, `QuadraticProgram` (cross-checked against `to_ising`), Aer `EstimatorV2`/`SamplerV2`, `AerSimulator.from_backend(FakeFez)`, `generate_preset_pass_manager` (opt level 3), `QiskitRuntimeService` + Runtime `Sampler` with dynamical decoupling and Pauli twirling, job mode (Open Plan, no sessions).

### 3. Measurable results vs classical

**Real IBM hardware (Q3, Scenario B, `ibm_marrakesh`, job `db3pk22mb58s73886f8g`, 4096 shots per circuit, 6 s QPU time):**

| p | 2-qubit gates | P(optimal) ideal simulator | P(optimal) real QPU | Approx. ratio (QPU) |
|---|---|---|---|---|
| 1 | 4 | 58.0% | 53.5% | 0.953 |
| 2 | 8 | 98.1% | 89.2% | 0.975 |
| 3 | 12 | 99.5% | 92.2% | 0.984 |

Uniform random guessing: 12.5%. The best plan found at every depth was the optimum, `[0, 20, 0]`, $9,175. Hardware noise lowers the success rate a little, as expected, but the result is far above random.

**Benchmark on 20 random grids** (seeds 1000-1019; Q18 QAOA on 3 instances), QAOA at p = 3. Accuracy = the method's plan is optimal. Full tables in [data/benchmarks/latest.md](data/benchmarks/latest.md) and on the dashboard's Benchmark page.

| Tier | Exact | Simulated annealing | No battery | Random sampling | QAOA ideal | QAOA noisy (FakeFez) |
|---|---|---|---|---|---|---|
| Q3 | 100% | 100% | 25% | 100%* | 100%* | 100%* |
| Q9 | 100% | 100%* | 25% | 100%* | 100%* | 100%* |
| Q18 | 100% | 100%* | 25% | 10% | 100%* | not run |

\*best-of-4096 samples. On a **single most-likely plan (top-1)** the picture differs: Q3 QAOA 85%, Q9 0-30%, Q18 0%, and on Q3 simulated annealing gets 100%. Success rate of one sample at p = 3 on Q9: QAOA 4.9% ideal vs 0.21% random (about 23x better than random, but far from certain).

**XY mixer experiment** (`python backend\scripts\run_mixer_compare.py Q9 Q18`; `qaoa.py: xy_mixer`, `xy_start_state`). The one-hot tiers waste most samples on invalid plans (30-60% valid at Q9). A Hamming-weight-preserving *XY mixer* with a W-state start only ever produces valid plans. Scenario B, ideal simulator, p = 1 / 2 / 3:

| Tier | Mixer | P(valid) | P(optimal) | Approx. ratio (all shots) | 2-qubit gates (p = 3, on chip) |
|---|---|---|---|---|---|
| Q9 | standard X | 30 / 37 / 62% | 1.6 / 2.6 / 4.9% | 0.12 / 0.19 / 0.35 | 336 |
| Q9 | XY | 100% | 4.4 / 3.5 / 3.5% | 0.88 / 0.89 / 0.89 | 502 |
| Q18 | standard X | 16 / 22 / 38% | 0.09 / 0.16 / 0.28% | 0.07 / 0.12 / 0.22 | 1,563 |
| Q18 | XY | 100% | 1.2 / 3.3 / 3.1% | 0.59 / 0.77 / 0.77 | 1,981 |

Honest reading: XY removes every invalid sample and raises plan quality a lot. But *a random valid plan* already has P(optimal) = 3.7% at Q9 (1/27) and 0.46% at Q18 (1/216), so on Q9 XY finds the optimum no more often than random-among-valid (and the standard mixer is slightly better at p = 3). On Q18 it is about 7x better than random-among-valid. Cost: 1.2-1.5x more two-qubit gates. It is an experiment on the simulator; the hardware run uses the standard mixer on Q3.

### 4. Quantum advantage: the honest answer

**There is no quantum advantage here, and we do not claim one.**

- Exact classical enumeration solves every tier in under 10 ms; the LP solves in about 50 ms. QAOA takes seconds to minutes (this is classical *simulation* time, not QPU time, and not a speed measurement).
- On Q3 and Q9, 4096 uniform random samples also find the optimum. QAOA's real value shows only as a higher probability per sample (e.g. 4.9% vs 0.21% on Q9).
- On Q9/Q18 the most likely QAOA sample is often *not* the optimum, and many shots are invalid plans (P(valid) 32-60% at p = 3).
- The problem is tiny: 3 hours, a handful of battery levels. A 3-hour battery path is a lookup, not a hard optimization problem.

**Scaling study** ([data/benchmarks/scaling.md](data/benchmarks/scaling.md); `python backend\scripts\run_scaling.py`). The grid is repeated to 3-15 hours (3-15 qubits for Q3, 9-15 for Q9), QAOA at p = 1 on the ideal simulator:

| Q3 hours (= qubits) | 3 | 6 | 9 | 12 | 15 |
|---|---|---|---|---|---|
| 2-qubit gates on an IBM Heron chip | 4 | 10 | 16 | 22 | 28 |
| QAOA P(optimal), p = 1 | 58% | 40% | 28% | 19% | 13% |
| Random guessing P(optimal) | 12.5% | 3.1% | 0.8% | 0.2% | 0.05% |
| Exhaustive enumeration | 0.3 ms | 2 ms | 25 ms | 0.25 s | 2.6 s |
| Classical dynamic programming | 0.04 ms | 0.06 ms | 0.09 ms | 0.12 ms | 0.2 ms |

- Circuit size grows linearly (the battery problem is a chain), and QAOA's success rate falls much more slowly than random guessing's. At 15 qubits it is about 270x better than a random guess. This is the encouraging part.
- But the same chain structure gives classical **dynamic programming**, which solves every size in about 0.2 ms with cost growing roughly linearly in the number of hours. It matched exhaustive enumeration on every row. A quantum advantage would have to beat *that*, not brute force. Not shown here, and not claimed.
- The one-hot Q9 encoding is much harder for QAOA: P(optimal) falls from 1.6% (3 hours) to 0.19% (5 hours), and the on-chip circuit has 95-189 two-qubit gates.

**Grover search: the one speedup we can measure** ([data/benchmarks/grover.md](data/benchmarks/grover.md); `python backend\scripts\run_grover.py`; dashboard page 06). Grover's algorithm needs about sqrt(N) queries where an unstructured classical search needs about N/2, a provable *quadratic* speedup. We implement Grover **adaptive** minimum search (Durr-Hoyer / BBHT): the oracle (a Qiskit `DiagonalGate`) marks every plan cheaper than the best found so far and the threshold is lowered after each improvement, so the search is never told the optimum. One query = one evaluation of the cost function. Over 200 runs per row (Scenario B):

| Size | Grover | Blind search of all bit patterns | Speedup | Classical search of valid plans only |
|---|---|---|---|---|
| Q3 (8 patterns) | 6.2 | 4.3 | 0.69x (slower) | 4.7 |
| Q9 (512 patterns) | 64.8 | 255.9 | 3.95x | 13.3 |
| Q18 (262,144 patterns) | 1,379 | 132,824 | 96x | 104 |
| Random grids, 3 to 15 hours | 5.8 to 172 | 4.6 to 3,711 | 0.79x to 21.6x, break-even about 4 qubits | |

Honest reading: this is a measured quadratic **query** speedup over *unstructured search of the qubit bitstring space*. It is **not** an advantage over the best classical solver: a classical search that only tries the valid battery plans needs far fewer queries (the one-hot encoding inflates the quantum search space, 2^18 patterns for 216 real plans), and dynamic programming beats every search. One Grover round costs 14 two-qubit gates at Q3 and 1,368 at Q9 on a Heron chip (FakeFez), so useful sizes need fault-tolerant hardware. The Grover state is computed with an exact formula verified against the Qiskit circuit (`tests/test_grover.py`), so these counts come from exact simulation, not from a quantum computer.

What an advantage would technically need (none of which this project demonstrates): problem sizes where exact methods become infeasible, circuits deep and clean enough to run on fault-tolerant or much lower-noise hardware, and evidence that QAOA's scaling beats the best classical heuristics. Q-GridOpt is a **working, honest end-to-end pipeline**, QUBO -> QAOA -> real QPU -> validated schedule, that makes that comparison possible as hardware matures.

---

## Where Qiskit is used

All Qiskit code lives in `backend/app/quantum/`. Each file starts with a `# QISKIT INTEGRATION:` comment.

| File | Qiskit component | Purpose |
|---|---|---|
| `quantum/qubo.py` | `qiskit_optimization.QuadraticProgram` | holds the QUBO |
| `quantum/ising.py` | `qiskit.quantum_info.SparsePauliOp` (cross-check: `to_ising`) | cost Hamiltonian |
| `quantum/qaoa.py` | `qiskit.circuit.library.qaoa_ansatz`, `qiskit_aer.primitives.EstimatorV2` | circuit + angle training |
| `quantum/aer_runner.py` | `qiskit_aer.AerSimulator`, `SamplerV2`, `AerSimulator.from_backend` | ideal and noisy simulation |
| `quantum/transpile.py` | `generate_preset_pass_manager`, `qiskit_ibm_runtime.fake_provider.FakeFez` | fit circuit to an IBM chip |
| `quantum/ibm_runner.py` | `QiskitRuntimeService`, Runtime `Sampler`, `least_busy`, error mitigation options | real hardware |
| `quantum/simulate.py` | all of the above | end-to-end QAOA runs |
| `quantum/decoder.py` | counts / bitstrings | bitstring -> battery path -> schedule |
| `quantum/grover.py` | `DiagonalGate` (oracle), `grover_operator`, `quantum_info.Statevector` | Grover adaptive minimum search |
| `quantum/draw.py` | `QuantumCircuit.draw("mpl")` | circuit diagrams for the dashboard |

The dashboard's **Quantum workflow** page shows each pipeline step with its Qiskit module, the circuit diagram, transpiled gate counts and the measurement histogram. Hardware results show an `IBM Quantum QPU` badge with the job id.

---

## Project layout

```
backend/app/
  grid/        scenario presets, merit-order dispatch, shared evaluator
  classical/   LP (PuLP/CBC), exact enumeration, no-battery, simulated annealing
  quantum/     QUBO, Ising, QAOA, Aer, transpile, IBM runner, decoder   <- all Qiskit code
  benchmark/   benchmark suite
  api/         FastAPI routes, async job worker
  store/       SQLite run store
backend/tests/ 203 tests
backend/scripts/  command-line runners
frontend/      React + Vite + TypeScript dashboard (no optimization logic)
data/          scenarios and benchmark results
docs/          manual verification, architecture diagram, pitch material
```

## Setup and run (Windows, cmd)

Requires Python 3.12 (not 3.14) and Node.js.

```
py -3.12 -m venv venv
venv\Scripts\activate.bat
pip install -r backend\requirements.txt
copy backend\.env.example backend\.env
```

Edit `backend\.env` with your IBM Quantum API key and instance CRN. This is only needed for real hardware; everything else works without it. Never commit `.env`.

Start the backend and the dashboard in two windows:

```
cd backend
uvicorn app.main:app --port 8000
```
```
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 (API docs at http://localhost:8000/docs).

Command-line scripts (from the project root):

| Command | What it does |
|---|---|
| `python backend\scripts\run_classical.py` | LP + no-battery baselines |
| `python backend\scripts\run_exact.py` | exact enumeration |
| `python backend\scripts\run_qaoa_sim.py` | QAOA on the ideal simulator |
| `python backend\scripts\run_noisy_sim.py` | QAOA with the FakeFez noise model |
| `python backend\scripts\run_benchmark.py` | benchmark suite (writes `data/benchmarks/`) |
| `python backend\scripts\run_scaling.py` | scaling study (3-15 hours) |
| `python backend\scripts\run_extended.py` | unit commitment / uncertainty / reserve study |
| `python backend\scripts\run_grover.py` | Grover adaptive search vs classical search (query counts) |
| `python backend\scripts\run_grover_ibm.py local` | 3-qubit Grover circuits on the FakeFez noise model (the `submit --yes` mode would use QPU time; not run) |
| `python backend\scripts\check_ibm.py` | check IBM account (read-only) |
| `python backend\scripts\run_ibm.py local` | hardware code path on a local fake backend |
| `python backend\scripts\run_ibm.py submit --yes Q3` | **real hardware run, uses QPU time** |
| `python backend\scripts\import_ibm_job.py <job_id>` | add a finished hardware job to the dashboard |

Tests: `cd backend && python -m pytest`

## Limitations

- Tiny problem (3 hours, 2-6 battery levels); no quantum advantage.
- QAOA decides only the battery trajectory; dispatch of other sources is a fixed classical rule.
- Hardware run is Q3 only (3 qubits) with angles trained on a noiseless simulator; Q9 and Q18 are simulated.
- QAOA times are classical simulation times, not QPU speed.
- The Grover speedup is over unstructured search only (see section 4); its query counts come from exact simulation, and the Q9 Grover circuit is too deep for today's hardware.
- Q18 QAOA was benchmarked on 3 instances (cost of simulation); the noisy simulation was not run for Q18.
- Battery efficiency is 100% in the default presets; no terminal state-of-charge value.
- Unit commitment covers one gas unit with a minimum output and a start-up cost; no minimum up/down times, ramp limits or multiple units.
- Uncertainty is three hand-set weather cases and an expected-cost objective; no calibrated forecast distribution, no risk measure beyond reporting the worst case.
- The reserve requirement is a spare-capacity margin, not a frequency, inertia or network (power-flow) model, so "grid stability" is only partly addressed.
- The unit-commitment tiers (12 and 18 qubits, 640-1,560 two-qubit gates) were run on simulators only; the real hardware run is the 3-qubit tier without unit commitment.
- One real hardware run (one job, 4096 shots per circuit); results would vary between runs and chips.
