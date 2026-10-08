# Q-GridOpt — Project Context for Claude Code

## What this is
Hackathon project (IBM Qiskit / IBM Quantum). Web app that optimizes a small renewable-energy
grid schedule (solar, wind, gas, battery over 3 periods) using a classical solver AND QAOA
(Qiskit Aer simulator + real IBM Quantum hardware), then compares them honestly.

Scientific claim (do not exceed it): "We formulate renewable-energy scheduling with battery
storage as a QUBO, solve it with QAOA on simulators and IBM Quantum hardware, and benchmark
against exact classical solvers." NEVER claim quantum advantage or speedup.

## The developer
- Comfortable with programming, NEW to quantum computing.
- When introducing any quantum concept (QUBO, Hamiltonian, QAOA, mixer, ansatz, transpilation,
  shots, noise), explain it first in PLAIN ENGLISH, then TECHNICAL.
- Prefers complete file contents over partial edits when showing code to review.
- Wants questions asked ONE AT A TIME, and all ambiguities resolved before writing code.

## Environment (Windows)
- OS: Windows, shell: Command Prompt (cmd). Use cmd-compatible commands
  (e.g. `venv\Scripts\activate.bat`, `copy`, `set VAR=value`), not bash or PowerShell-only syntax.
- Project root: D:\dev\q-gridopt (not inside OneDrive). Paths inside the project are relative.
- The system default Python is 3.14 (too new for Qiskit Aer wheels). ALWAYS use Python 3.12
  via `py -3.12`. Never create or use a venv with 3.14. Verify `python --version` shows 3.12
  inside the venv before installing anything.
- The venv lives at the project root: `venv\` and is already activated when Claude Code starts.
- Node.js v24 is installed (fine for Vite/React). Git and Claude Code are installed.
- Keep every script runnable from cmd; avoid bash-only commands.

## Working rules (MANDATORY)
1. Work strictly stage by stage (see Roadmap). Never start the next stage without explicit
   confirmation from me.
2. At the end of every stage, report: what was built, files created/changed (with paths),
   install commands, run commands, expected output, troubleshooting tips. Then STOP and wait.
3. Run tests yourself before reporting a stage as done. Show me the actual output.
4. Do not invent or use deprecated APIs. Before using any Qiskit / qiskit-aer /
   qiskit-ibm-runtime / qiskit-optimization API, check the installed version (pip show) and
   verify the function/class exists in that version. If something changed, tell me.
5. Never put secrets in code. IBM credentials only in backend/.env (gitignored).
6. Never manipulate results to make quantum look better. If classical wins, show it.
7. The frontend must contain NO optimization logic.
8. Never submit anything to IBM hardware until the same circuit works on Aer (ideal + noisy)
   and I approve the hardware run (it consumes limited QPU time).
9. After each completed stage, update the "Current status" section at the bottom of this file.

## Grid dataset (default preset "Scenario B"; each period = 1 hour, so MW == MWh)
| Period    | Demand | Solar | Wind |
|-----------|--------|-------|------|
| Morning   | 80     | 30    | 20   |
| Afternoon | 120    | 120   | 20   |
| Evening   | 150    | 10    | 40   |

Also provide preset "Scenario A" (original): afternoon solar = 90 (no surplus, battery unused).
Gas capacity 100 MW (no min output in MVP). Battery capacity 50 MWh, max charge/discharge
rate 30 MW, initial SOC 0, efficiency 100% (configurable later).
All values must be configurable via API/UI.

## Model
Variables per period t: solar s_t, wind w_t, gas g_t, charge c_t, discharge d_t, unserved u_t.
Constraints:
- Balance: s_t + w_t + g_t + d_t − c_t + u_t = D_t
- 0 ≤ s_t ≤ S_t, 0 ≤ w_t ≤ W_t, 0 ≤ g_t ≤ Gmax, 0 ≤ c_t,d_t ≤ rate
- SOC_t = SOC_{t−1} + c_t − d_t, 0 ≤ SOC_t ≤ capacity, SOC_0 given
- u_t ≥ 0
Curtailment k_t = (S_t − s_t) + (W_t − w_t).
Objective ($, all weights configurable):
  60·gas + (50 $/t × 0.45 tCO2/MWh)·gas + 10·curtailment + 5·discharge + 1000·unserved

## Expected results (use as test targets)
- Optimal: Morning solar30 wind20 gas30; Afternoon solar120 (20 to battery) wind20 gas0,
  charge 20; Evening solar10 wind40 discharge20 gas80. Objective $9,175
  (gas $6,600 + CO2 $2,475 + wear $100), CO2 49.5 t, curtailment 0.
- No-battery baseline: gas 130, curtail 20, objective $10,925.

## Architecture rules
- ONE shared evaluator: evaluate(scenario, schedule) computes cost, CO2, curtailment,
  renewable utilization, violations, objective. EVERY solver's output is scored by it.
- Merit-order dispatch rule (per period, given battery net flow b): renewables first,
  gas up to Gmax, remainder unserved, surplus curtailed.
- Every result has `source`: classical_lp | classical_exact | classical_no_battery |
  aer_statevector | aer_noisy | ibm_hardware, plus provenance (backend name, job id,
  timestamp, shots, library versions).

## Classical baselines
1. LP with PuLP (CBC) on the continuous model.
2. Exact enumeration of the discretized battery-path problem (same problem QAOA solves).
3. No-battery greedy dispatch.

## Quantum formulation (state-path encoding)
QAOA decides the battery trajectory; merit-order rule fills in each period (state this openly).
Binary variable y_{t,l} = 1 if battery SOC at end of period t equals level l.
QUBO energy = Σ_l F_1(l − SOC_0)·y_{1,l} + Σ_{t≥2} Σ_{a,b} F_t(b − a)·y_{t−1,a}·y_{t,b}
            + A·Σ_t (1 − Σ_l y_{t,l})²
F_t(b) = full $ cost of period t under merit order with battery change b
(+ large penalty if |b| > rate). A ≈ 1.5 × max total cost (configurable, shown in UI).
Tiers:
- Q3: levels {0,20}, one bit per period, no one-hot penalty, 3 qubits, chain couplings → HARDWARE
- Q9: levels {0,20,40} one-hot, 9 qubits → main simulator result, stretch hardware
- Q18: levels 0..50 step 10 one-hot, 18 qubits → simulator stress test
REQUIRED TEST: for every valid bitstring, QUBO energy == evaluator objective (exhaustive).

## QAOA
- Ising conversion x = (1 − Z)/2 → SparsePauliOp; cross-check with qiskit-optimization to_ising.
- Circuit: QAOAAnsatz (verify current API), reps p = 1..3, mixer Σ X.
- Train γ, β on StatevectorEstimator with SciPy COBYLA (CVaR optional).
- Sample with Aer SamplerV2; noisy sim with AerSimulator.from_backend.
- Hardware: QiskitRuntimeService(channel="ibm_quantum_platform"), least_busy backend,
  generate_preset_pass_manager, SamplerV2 in job or Batch mode (Open Plan: NO sessions).
  Fixed (simulator-trained) parameters on hardware. Enable dynamical decoupling / twirling
  only if supported by the installed version.
- Metrics: best schedule found, P(optimal), valid-shot fraction, approximation ratio,
  comparison vs uniform random sampling, circuit depth & 2-qubit gate count (pre/post transpile).

## Qiskit visibility requirement (hackathon rule)
All Qiskit code lives in backend/app/quantum/. Each quantum file starts with a comment:
"# QISKIT INTEGRATION: <what this file uses Qiskit for>". The README must contain a
"Where Qiskit is used" table (file -> Qiskit component -> purpose). The dashboard must show:
Quantum Workflow page (pipeline steps labelled with Qiskit modules), circuit diagram (SVG),
transpiled stats, measurement histogram, source badge + IBM job ID on hardware results.

Planned Qiskit touchpoints:
| File | Qiskit component | Purpose |
|------|------------------|---------|
| quantum/qubo.py | qiskit_optimization.QuadraticProgram | hold the QUBO |
| quantum/ising.py | qiskit.quantum_info.SparsePauliOp | cost Hamiltonian |
| quantum/qaoa.py | qiskit.circuit.library.QAOAAnsatz, StatevectorEstimator | circuit + training |
| quantum/aer_runner.py | qiskit_aer AerSimulator, SamplerV2 | ideal + noisy simulation |
| quantum/transpile.py | generate_preset_pass_manager | fit circuit to IBM chip |
| quantum/ibm_runner.py | qiskit_ibm_runtime QiskitRuntimeService, SamplerV2, Batch | real hardware |
| quantum/decoder.py | counts / bitstrings | bitstring -> battery path -> schedule |

## Tech stack
Backend: Python 3.12, FastAPI, Pydantic v2, Uvicorn, NumPy, SciPy, PuLP, SQLite, pytest.
Quantum: qiskit>=2,<3, qiskit-aer, qiskit-ibm-runtime, qiskit-optimization>=0.7,
matplotlib, pylatexenc.
Frontend: React + Vite + TypeScript, Tailwind, Recharts, React Router, TanStack Query.
Dark "grid control room" style; not a generic AI dashboard.

## API
GET  /api/health
GET  /api/scenarios/presets
POST /api/qubo/preview
POST /api/runs/classical
POST /api/runs/quantum/simulator
POST /api/runs/quantum/ibm        (202 + run_id, async)
GET  /api/runs/{run_id}
GET  /api/runs

## Structure
q-gridopt/
  backend/app/{main.py, config.py, models/, grid/, classical/, quantum/, api/, store/}
  backend/tests/
  backend/requirements.txt, backend/.env (gitignored)
  frontend/src/{pages/, components/, charts/, api/, types/}
  data/scenarios/*.json
  docs/
  CLAUDE.md, README.md, .gitignore

## Roadmap
0. Environment + .gitignore + requirements + IBM account check
1. Scenario models, merit-order dispatch, shared evaluator (reproduce $9,175 and $10,925)
2. LP solver + no-battery baseline
3. Manual verification + discrete exact enumerator
4. QUBO builder (Q3/Q9/Q18) + Ising conversion + exhaustive energy test
5. QAOA on Aer statevector (p=1..3), compare vs random sampling
6. Decoder + metrics + noisy simulation
7. IBM hardware run (Q3; Q9 if budget allows) — only after my approval
8. FastAPI endpoints + async hardware jobs + tests
9. React dashboard
10. README, architecture diagram, pitch material, limitations

## Current status
Stage 0 DONE (2026-10-08): folder structure, .gitignore, backend/requirements.txt,
backend/.env.example, backend/scripts/check_env.py (all checks pass).
Installed: qiskit 2.5.2, qiskit-aer 0.17.2, qiskit-ibm-runtime 0.50.0,
qiskit-optimization 0.7.0, pulp 4.0.0 + cbcbox 2.935 (requirement `pulp[cbc]>=4,<5`;
superseded the Stage 0 pin to 3.x because 3.3.2 deprecates PULP_CBC_CMD/LpVariable()).
PuLP 4 API: prob.add_variable(...), prob.solve(pulp.COIN_CMD(msg=False)) -> LpSolveStats,
stats.status == pulp.LpSolveStatus.Optimal (pulp.LpStatus and prob.status no longer exist).
IBM account check script written (backend/scripts/check_ibm.py, read-only) but not yet run:
needs backend/.env with real key + CRN. IBM trial showed "expires in 1 day" on 2026-10-08;
hardware (Stage 7) is an optional bonus — hackathon only requires Qiskit integration.

Stage 1 DONE (2026-10-08): models (app/models/grid.py, evaluation.py), merit-order dispatch
(app/grid/dispatch.py), shared evaluator (app/grid/evaluator.py), presets
(app/grid/presets.py + data/scenarios/scenario_{a,b}.json). 22 pytest tests pass
(run: cd backend && python -m pytest). Reproduces $9,175 (B, battery 0->20->0) and
$10,925 (B, no battery). Scenario A: $11,550 without battery, $11,650 with 0->20->0.
Decisions: solar dispatched before wind; efficiency applies on charging
(SOC += eff*charge - discharge); evaluator objective is pure $ cost, rule breaches are
reported as violations (feasible=False), unserved demand is penalised not a violation.

Stage 2 DONE (2026-10-08): SolverResult/Provenance model (app/models/result.py,
app/provenance.py), LP solver (app/classical/lp.py, source classical_lp) and no-battery
baseline (app/classical/no_battery.py, source classical_no_battery). Both scored by the
shared evaluator. 44 tests pass (incl. LP <= every feasible discrete path, LP <= no-battery
on 15 random scenarios). LP: B $9,175, A $11,550 (battery idle). Script:
backend/scripts/run_classical.py.

Stage 3 DONE (2026-10-08): docs/manual_verification.md (hand calcs of $10,925, $9,175,
$11,550, ranking spot checks, why 20 MWh is optimal). Exact enumerator
app/classical/exact.py (source classical_exact; enumerate_paths + solve_exact, reports all
tied optimal paths, n_paths/n_feasible/mean/worst for later QAOA metrics). Tier levels in
app/grid/tiers.py (Q3 {0,20}, Q9 {0,20,40}, Q18 {0..50 step 10}). 67 tests pass.
B: all tiers -> unique optimum SOC [0,20,0] $9,175 (= LP). A: [0,0,0] $11,550.
Feasible paths: Q3 8/8, Q9 12/27, Q18 107/216 (rest break the 30 MW rate).
Script: backend/scripts/run_exact.py [preset]. No terminal SOC value (leftover energy = $0).

Stage 4 DONE (2026-10-08): app/quantum/qubo.py (build_qubo -> QuboModel holding a
qiskit_optimization QuadraticProgram; Q3 binary 1 bit/hour, Q9/Q18 one-hot; variable k =
t*L + level index; F_t uses the evaluator's period_costs + dispatch battery_flows),
app/quantum/ising.py (own x=(1-Z)/2 conversion -> SparsePauliOp + offset, cross-checked vs
qiskit_optimization to_ising; ising_energies() for all basis states). Variable i = qubit i.
Penalty decision (user-approved test design): ONE constant A for one-hot breaks AND
rule-breaking hours (rate limit / discharge > demand); default A = 1.5 x max $ over all
paths of the tier (configurable). Exhaustive test: feasible path -> energy == evaluator $;
rule-breaking path -> energy == evaluator $ + A x (bad hours). Ground state over all 2^n
bitstrings = exact optimum (unique) for Q3/Q9/Q18, both presets. 103 tests pass.
Scenario B: A = $49,312 (Q3), $82,238 (Q9), $98,700 (Q18); Ising terms 5 / 34 / 131;
Q3 has chain ZZ couplings only (0-1, 1-2). Script: backend/scripts/show_qubo.py [preset].

Stage 5 DONE (2026-10-08): app/quantum/qaoa.py (qaoa_ansatz FUNCTION - the QAOAAnsatz class
is deprecated since Qiskit 2.1; params named β[i]/γ[i], sorted β first -> always bind by name;
H scaled by max|coef| for training, energies reported in $). USER-APPROVED DEVIATION: training
uses qiskit_aer EstimatorV2 in exact mode (statevector, approximation=True, precision=0) for
ALL tiers instead of StatevectorEstimator (identical to 1e-13, ~50x faster on Q18; test
enforces agreement). Training: p=1 grid 24x12 + COBYLA from best 3; p>1 INTERP warm start +
2 random starts; COBYLA maxiter 300. app/quantum/aer_runner.py (Aer SamplerV2 ideal sampling,
exact probabilities from saved statevector), app/quantum/decoder.py (index k = int(key,2),
qubit i = bit i; path_table, distribution_stats used for BOTH QAOA and uniform random),
app/quantum/simulate.py (run_qaoa_simulation / run_depth_sweep -> SolverResult source
aer_statevector; schedule = cheapest feasible SAMPLED path; schedule may be None if none).
Defaults: 4096 shots, seed 1234. 116 tests pass. Script: backend/scripts/run_qaoa_sim.py.
Scenario B results (P(optimal) exact, p=1/2/3): Q3 58.0/98.1/99.5% (random 12.5%);
Q9 1.6/2.6/4.9% (random 0.20%; most likely path at p=3 is NOT the optimum);
Q18 0.09/0.16/0.28% (random 0.0004%, ~730x at p=3; P(valid) 38% at p=3; QAOA samples found
$9,175, 4096 random shots only found $20,725; Q18 sweep ~3 min).
Honest notes: on Q3/Q9, 4096 uniform random shots also find the optimum; exact classical
enumeration solves every tier in <10 ms. No quantum advantage claimed.

Stage 6 DONE (2026-10-08): app/quantum/transpile.py (generate_preset_pass_manager opt level 3,
fake_backend() from qiskit_ibm_runtime.fake_provider, default FakeFez = Heron 156q CZ;
circuit_stats: depth, 2q gates, 2q depth, active qubits; "logical" = native gates without
routing, "transpiled" = on chip). aer_runner: transpile_measured (measure_all BEFORE
transpiling keeps clbit i = logical qubit i), sample_noisy (SamplerV2.from_backend(
AerSimulator.from_backend(backend))), sample_transpiled_ideal (isolates noise vs transpile).
decoder: approximation ratio, USER-APPROVED definition: AR = (C_worst - E[C])/(C_worst - C_opt)
over ALL shots, invalid/infeasible shots scored as C_worst; also approximation_ratio_feasible.
simulate.run_noisy_simulation(scenario, ideal_result, backend_name) -> source aer_noisy with
FIXED ideal-trained angles. Ideal results now include details["circuit"]. 126 tests pass.
Scenario B, FakeFez, p=1/2/3: Q3 on-chip 2q gates 4/8/12 (no SWAPs needed), P(opt) ideal
58/98/99.5% -> noisy 55/94/94%, AR noisy 0.956/0.990/0.988. Q9 on-chip 2q 86/200/336,
P(opt) ideal 1.6/2.6/4.9% -> noisy 1.6/1.5/2.4%, AR (all shots) ideal .117/.190/.349 ->
noisy .104/.142/.179 (random AR 0.015). Q18 on-chip 2q 430/1064/1563 (noisy sim not run:
stats only). Script: backend/scripts/run_noisy_sim.py [preset] [FakeBackend] [tiers...].
Q3 is the clear hardware candidate.

Stage 7 CODE DONE, HARDWARE RUN NOT YET DONE (2026-10-08): backend/.env exists but still has
placeholders. API CHANGE: qiskit_ibm_runtime.SamplerV2 is DEPRECATED in 0.50.0 -> use
qiskit_ibm_runtime.executor_sampler.Sampler (same mode/options/run interface; supports
dry_run=True = server-side validation + job.usage_estimation["quantum_seconds"], no QPU used).
app/config.py (load_ibm_credentials from backend/.env, repr hides key; RUNS_DIR backend/runs/).
app/quantum/ibm_runner.py: get_service, select_backend (least_busy), prepare (transpile + bind
FIXED ideal angles), make_sampler (DD XpXm + gate/measure twirling on real backends only),
estimate_qpu_seconds (dry run), submit (real backend REQUIRES confirm=True else NotApproved;
records job to backend/runs/ibm_jobs.json), collect / collect_recorded(job_id).
Job mode, one job with p=1..3 as 3 pubs (no sessions). Fake backend => source aer_noisy,
never ibm_hardware. Twirling may round shots up; actual shots read from counts.
Script backend/scripts/run_ibm.py: local | estimate | submit --yes | collect <job_id>.
Local test on FakeFez (Q3): P(opt) 57.5/94.2/95.0%, AR .960/.988/.990. 134 tests pass.
Remaining for Stage 7: user fills backend/.env -> check_ibm.py -> run_ibm.py estimate (dry run,
ask user first) -> user approves -> run_ibm.py submit --yes Q3.

Stage 8 DONE (2026-10-08): FastAPI app (app/main.py create_app(db_path), lifespan, CORS for
Vite :5173), app/api/routes.py, app/api/schemas.py, app/api/jobs.py (single-thread Worker),
app/store/db.py (SQLite RunStore; default backend/runs/qgridopt.sqlite, env QGRIDOPT_DB),
app/quantum/draw.py (circuit SVG via draw("mpl"), only <= 9 qubits).
USER-APPROVED DEVIATION: BOTH /runs/quantum/simulator and /runs/quantum/ibm are async
(202 + run_id; poll GET /api/runs/{id}; status queued/running/submitted/completed/failed +
progress text). /runs/classical is sync (201). Requests take {preset} OR {scenario}.
/qubo/preview returns QUBO terms, prettyprint text, Ising terms, ground state (bitstring in
Qiskit order), circuit SVG + circuit stats. IBM endpoint: real backend needs confirm=true AND
credentials (else 400); backend "Fake*" = local testing mode (source aer_noisy). GET of a
'submitted' IBM run not tracked by the worker (server restart) asks IBM and collects it.
API CHANGES found: QuadraticProgram.export_as_lp_string() deprecated -> prettyprint();
Starlette TestClient deprecates httpx -> requirements now httpx2>=2.13,<3.
Run: cd backend && uvicorn app.main:app --reload --port 8000 (docs at /docs).
152 tests pass (~70 s). Live server verified with HTTP calls.

Stage 9 DONE (2026-10-08): frontend/ React 19.3 + Vite 8.3 + TypeScript 7.0 + Tailwind 4.3
(@tailwindcss/vite, theme tokens in src/index.css @theme) + React Router 8.4 (RouterProvider
from "react-router/dom") + TanStack Query 5.104 + Recharts 3.10, IBM Plex fonts via
@fontsource (offline). Exact versions pinned in frontend/package.json. Vite proxies /api to
API_TARGET (default http://localhost:8000); PORT env sets the dev port. Vite listens on
localhost (IPv6 ::1), use http://localhost:5173 not 127.0.0.1.
Pages: / (scenario editor + classical LP/no-battery/exact), /quantum (Qiskit pipeline steps,
tier picker, QUBO preview, circuit SVG, transpile stats, Ising terms, async simulator run,
QuantumResults), /hardware (local FakeFez test; real run needs IBM creds + approval checkbox
-> confirm=true, approval resets after one submit), /runs and /runs/:id (provenance).
Frontend has NO optimisation logic: backend added details["histogram"] (decoder.histogram:
decoded top bitstrings with path/objective/feasible/optimal flags).
Run: cd frontend && npm install && npm run dev. Build: npm run build (tsc + vite). Pages are
lazy-loaded (React.lazy + Suspense in Layout); no chunk-size warning. Proxy default target is
http://127.0.0.1:8000 (uvicorn is IPv4-only; Node resolves localhost to ::1 first). Verified: tsc clean, build OK, all 22 modules compile via Vite, every UI API
call works through the proxy. NOT visually inspected by Claude (Chrome extension not
connected) - user to check the look. 153 backend tests pass.
Post-stage-9 fixes (2026-10-08): GET / on the API redirects to /docs (users opened :8000 and saw
404); pages lazy-loaded; proxy default 127.0.0.1.

HARDWARE (2026-10-08): user first said "hardware not there", then connected their IBM account:
check_ibm.py PASSED (ibm_fez / ibm_kingston / ibm_marrakesh, 600 s QPU remaining, 0 jobs). The
CRN line in backend/.env had been commented out with '#'; fixed. check_ibm.py now masks the CRN.
Dry run is NOT available on this account (needs IBM 'mock_<backend>' device -> 404); handled:
estimate_qpu_seconds returns None. Every real job now has HardwareOptions.max_execution_time =
60 s (IBM force-cancels beyond it) = worst-case QPU usage. Real Q3 run awaits explicit approval.
Never describe results as run on a QPU unless a real ibm_hardware result exists.

GRADING CRITERIA (user, 2026-10-08): 1 novelty, 2 level of Qiskit programming, 3 measurable
results benchmarked vs classical (result table), 4 "what quantum advantage technically" ->
answer HONESTLY (no advantage at this size; scaling argument; what's missing). Agreed plan:
(1) benchmark suite + simulated annealing, (2) XY mixer, (3) real IBM Q3 run, (4) scaling
study, (5) Stage 10 README/pitch organised by the 4 criteria. One item at a time.

Item 1 benchmark suite (2026-10-08): app/classical/annealing.py (own NumPy simulated annealing on
the SAME QUBO, reads = shots, 100 sweeps, geometric schedule T_hot = maxΔ/ln2 -> 1e-4 T_hot;
source classical_annealing). app/benchmark/suite.py (random_scenario(seed): 3 periods, values in
steps of 5 MW, default battery/costs; run_suite: exact, annealing, random (analytic), QAOA ideal
p=1..3, QAOA noisy FakeFez; LP per instance; metrics p_optimal, found_optimum, AR, p_valid,
best_gap, samples_99 = ceil(ln .01/ln(1-p)), time (QAOA time = classical simulation, not QPU)).
Results -> data/benchmarks/latest.md / latest.json / timestamped json.
Script: backend/scripts/run_benchmark.py [--instances N --tiers .. --q18-qaoa K --no-noise].
Fixed bug: decoder.index_of overflowed with NumPy int8 bits (now int(b) << i).
User asked for Accuracy / F1 / result table: every method gives a top-1 plan (most likely
valid) and best-of-N plan (best feasible sample). accuracy_top1/best = plan is optimal;
F1 = macro-F1 of hourly battery decisions (charge/idle/discharge) vs the optimal plan
(tied optima: the method's own optimal plan counts as truth; missing plan = 'none' = wrong).
Methods now also include lp (continuous, never worse) and no_battery ("always idle").
summary + headline (QAOA at max p) in latest.json; markdown has definitions, headline,
per-tier full tables. API GET /api/benchmarks/latest (?rows=true for per-instance rows);
dashboard page 05 Benchmark (/benchmark). 170 backend tests pass.
REAL HARDWARE RUN DONE (2026-10-08, user-approved): Q3, scenario_b, backend ibm_marrakesh, job id
db3pk22mb58s73886f8g, source ibm_hardware, 3 circuits (p=1..3) x 4096 shots, QPU usage 6 s
(of 600 s). P(optimal) ideal -> hardware: p=1 58.0 -> 53.5%, p=2 98.1 -> 89.2%, p=3 99.5 -> 92.2%
(uniform random 12.5%). AR hardware .953/.975/.984. Best found at every p: [0,20,0] $9,175.
Recorded in backend/runs/ibm_jobs.json. Remaining plan: XY mixer, scaling study, Stage 10 README.

README DONE (2026-10-08): README.md written (claim, how it works, 4 grading criteria with hardware +
benchmark tables, honest no-advantage section, Where Qiskit is used table, setup/run, limitations).
Also: scripts/import_ibm_job.py (hardware job -> dashboard DB), Hardware page "Previous real hardware
runs" panel, Runs/Pipeline layout fixes. Still optional: XY mixer, scaling study, architecture diagram,
pitch material (Stage 10 remainder).

OPTIONAL ITEMS DONE (2026-10-08): (a) scaling study: scripts/run_scaling.py -> data/benchmarks/scaling.{md,json}
(Q3 3-15 hours, Q9 3-5 hours; QAOA p=1; DP over battery level matches enumeration, ~0.2 ms; QAOA P(opt) 58% -> 13%
at 15 qubits vs random 0.05%). (b) XY mixer: qaoa.py xy_mixer/xy_start_state (W-state start; a single-plan start
got stuck at P(opt)=0), cost_for(..., mixer="xy"), run_qaoa_simulation(mixer=), scripts/run_mixer_compare.py,
tests/test_xy_mixer.py. Result: P(valid) 100%, AR much higher, but P(opt) on Q9 ~ random-among-valid (3.7%);
Q18 ~7x over random-among-valid. Not exposed in the API/UI (simulator-only experiment). (c) docs/architecture.md
(mermaid) and docs/pitch.md. README updated. 177 tests pass. Project is not a git repo (user decides on GitHub).

USE CASE 04 EXTENSION DONE (2026-10-08, user-approved "fix all things"): optional model features, all off by default
(Scenarios A/B and every old number unchanged), all on in new preset scenario_c: (1) unit commitment (gas on/off,
min_output 40, startup $800), (2) forecast uncertainty (3 weighted solar/wind cases; battery+commitment first stage,
dispatch recourse; objective = expected cost, worst case reported), (3) reserve margin (10% of demand, $50/MW).
Code: models/grid.py (UnitCommitment, Uncertainty, Reserve, PeriodDispatch.gas_on), grid/dispatch.py, grid/evaluator.py
(outcome_parts = ONE cost formula shared with the QUBO), models/evaluation.py, grid/tiers.py (Q3U 12 qubits, Q9U 18),
quantum/qubo.py (state = (level, gas on/off), one-hot; QuboModel.states/commit/decode_states), quantum/decoder.py
(PathInfo.commits, schedule_for), classical/exact.py (commit enumeration), classical/lp.py (_solve_extended = two-stage
stochastic MILP, CBC; GapLimit status accepted with gapRel 1e-9), api (Tier adds Q3U/Q9U; exact_tiers default depends on
scenario; IBM endpoint rejects U tiers), frontend (types, scenario editor toggles, tier picker, ClassicalSummary
start-ups/reserve/forecast-case table). scripts/run_extended.py -> data/benchmarks/extended.{md,json}. tests/test_extended.py
(26 tests); 203 tests pass. Findings: each feature changes the plan/cost; best Scenario C plan = battery [0,20,0], gas on
all day, $14,784 (exact), MILP $14,096; QAOA samples the exact optimum but annealing has higher P(optimal) than QAOA on
Q3U/Q9U; no advantage. NOT done: min up/down times, ramp limits, multiple units, network/frequency model, hardware run
of U tiers. UI not visually inspected by Claude (user to check Scenario C in the dashboard).

UI REDESIGN DONE (2026-10-08, user asked for a polished, less "vibe-coded" look): new design system in
frontend/src/index.css ("aurora control room": aurora background, glass panels, Space Grotesk display font via
@fontsource/space-grotesk 5.3.0, gradient accents, entrance animations; token names unchanged so old classes work).
New: components/icons.tsx, components/GridFlow.tsx (animated hour-by-hour power-flow diagram from the schedule),
components/HardwareHero.tsx (latest REAL QPU run vs ideal simulator vs random), restyled ui.tsx (PageHeader, Panel,
Stat KPI cards, Chip, Button), Layout (floating glass sidebar with icons), Pipeline (phase-coloured steps), Quantum tier
cards, Benchmark heat tiles, Run log filter chips, charts (gradients, rounded bars, glass tooltips), collapsible scenario
editor. Overview auto-solves on load/preset change only (edits light up a re-run button; each solve is a run-log row).
api.runs now takes kind + limit (default 200) so the hardware run is never pushed out of the list by classical runs.
Visually checked in Chrome (Overview A/C, Quantum, Hardware, Benchmark, Runs). tsc + vite build clean.

GROVER STAGE DONE (2026-10-08, user chose "Option A" = adaptive minimum search): app/quantum/grover.py (Grover Adaptive
Search, Durr-Hoyer + BBHT schedule: oracle = qiskit DiagonalGate marking energy < threshold, amplification =
qiskit.circuit.library.grover_operator, Statevector for checks). Exact closed form sin^2((2j+1)theta) with uniform
spread inside marked/unmarked sets, verified against the Qiskit circuit (tests/test_grover.py, 16 tests; 219 total pass).
Query unit = one cost evaluation (oracle round or classical check). scripts/run_grover.py -> data/benchmarks/grover.{md,json}
(200 runs/row). Results (Scenario B): Q3 GAS 6.2 vs blind 4.3 queries (slower, N=8); Q9 64.8 vs 255.9 (3.95x vs blind) but
13.3 for a structure-aware classical search (0.21x); Q18 1,379 vs 132,824 (96x vs blind) but 104 structured (0.08x).
Random-hours Q3-encoding grids 3-15 h: speedup vs blind 0.79x -> 21.6x, break-even ~4 h, fitted slope 0.42 vs 0.82.
Honest reading: provable quadratic QUERY speedup over unstructured search of the 2^n bitstring space; NOT over classical
methods that use the problem structure (valid plans only, dynamic programming). The one-hot encoding inflates the quantum
search space. Oracle on FakeFez: Q3 14 two-qubit gates, Q9 1,368 per iteration (not runnable on today's QPUs at Q9).
Follow-ups DONE (2026-10-08): GET /api/benchmarks/grover + dashboard page 06 'Grover search' (pages/Grover.tsx), README section 4 + Qiskit table + commands + limitations, docs/pitch.md line. Hardware path BUILT BUT NOT RUN: app/quantum/grover_ibm.py + scripts/run_grover_ibm.py (local | submit --yes | collect; 3 circuits j=0/1/2 rounds on Q3, 4096 shots, capped 60 s, needs confirm=True). Local FakeFez result: 12.0 / 75.4 / 85.7% vs ideal 12.5 / 78.1 / 94.5% (data/benchmarks/grover_local.json, labelled simulation). USER DECLINED the real QPU run on 2026-10-08 (594 s of QPU time remained): do not describe Grover as run on hardware.
