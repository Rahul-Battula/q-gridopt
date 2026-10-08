# Pitch material

## 30-second version

A power grid has to match supply and demand every hour. Solar produces too much at noon and too little in the evening, so we need a battery, and we need to decide when to charge and discharge it. We turned that decision into a problem a quantum computer can attack (a QUBO), solved it with QAOA in Qiskit, and ran it on a real IBM quantum computer. It found the optimal plan, saving about $1,750 and 20 MWh of gas against having no battery. We compared it to classical solvers and tell you honestly: at this size, classical wins, and we claim no quantum advantage. What we built is the full, verified pipeline.

## One-line answer to "does it cover the brief?"

The brief is grid load balancing **and unit commitment** with variable renewables. We model hourly supply-demand balance, battery dispatch, a gas unit with on/off commitment, minimum output and start-up cost, weather uncertainty (expected cost over three forecast cases) and a reserve margin. QAOA chooses the battery plan and the commitment; classical dispatch fills in the rest (hybrid). Cost, CO2 and curtailment are reported for every plan. Limits: one gas unit, three hours, no network model, so "stability" means a reserve margin only.

## Slide outline (9 slides)

1. **Problem.** Grid, solar surplus at noon, evening peak. Show the 3-hour table.
2. **Idea.** Battery plan as qubits: one variable per (hour, battery level). Show the QUBO sentence.
3. **Pipeline.** The diagram from `docs/architecture.md`, with Qiskit components labelled.
4. **Correctness.** Exhaustive test: QUBO energy equals the evaluator's dollar cost for every plan; ground state equals the exact optimum.
5. **Real hardware.** Table: ideal 58 / 98 / 99.5% -> real `ibm_marrakesh` 53.5 / 89.2 / 92.2% (p = 1 / 2 / 3), random 12.5%. Job id on the slide.
6. **Benchmark.** 20 random grids, every method, accuracy / F1 / success rate. Show where classical wins.
7. **Honest answer on quantum advantage.** Classical solves it in milliseconds; a dynamic-programming algorithm solves the chain problem in polynomial time (see the scaling study); what would be needed for an advantage.
8. **Beyond the toy model (Use Case 04).** Unit commitment, uncertainty, reserve (Scenario C): what each feature changes in the plan and cost table, and the dashboard's forecast-case table.
9. **What's next.** Better mixers (XY), more units and hours, network constraints, lower-noise hardware.

## Live demo script (3 minutes; 4 if you show Scenario C)

1. **Grid & classical** page: show the scenario and the classical optimum, $9,175 versus $10,925 with no battery.
2. **Quantum workflow** page: walk the 9 steps and point at the Qiskit module in each box. Show the circuit diagram.
3. **IBM hardware** page: show "Previous real hardware runs", then open the run. Point out the `IBM Quantum QPU` badge and the job id. **Do not press Submit.**
4. (Optional) Pick **Scenario C** in the scenario dropdown on the first page: the dashboard shows start-ups, the reserve shortfall and the forecast-case table. On the Quantum workflow page use tier Q3U.
5. **Benchmark** page: show the result table and read the headline row.
6. **Run log:** every result with its provenance.

## Questions judges may ask

**Is this a quantum advantage?** No. Exact classical enumeration takes under 10 ms and the problem is a chain, so dynamic programming scales polynomially. We built a verified QAOA pipeline and measured it on real hardware. The advantage question needs far larger, less noisy machines. What we *can* show is Grover search, which needs about sqrt(N) cost evaluations where blind classical search needs N/2: a measured 96x fewer queries at 18 qubits (21.6x on 15-hour grids, break-even near 4 qubits). That is a speedup over unstructured search only; a classical search that uses the problem structure still needs fewer queries, and one Grover round is too deep for today's chips at 9 qubits.

**Do you model unit commitment?** Yes, in Scenario C: the gas unit is on or off each hour, runs at least 40 MW while on, and costs $800 per start-up. The on/off decision is part of the quantum state (tiers Q3U, 12 qubits, and Q9U, 18 qubits), the exact solver, and a mixed-integer program. Not modelled: minimum up/down times, ramp limits, several units.

**How do you handle uncertainty?** Three weighted weather cases; the battery plan and the commitment are fixed first, dispatch reacts to the case that happens, and the objective is the expected cost (the worst case is reported too). The best plan keeps the gas unit on all day, because the cheaper on/off/on plan can leave demand unserved if the forecast is wrong.

**Did the unit-commitment version run on real hardware?** No. Its circuits need 640-1,560 two-qubit gates, far too deep for today's chips; those tiers are simulator-only. The real hardware run is the 3-qubit tier.

**Why did the real chip do worse than the simulator?** Hardware noise (gate and readout errors). It dropped from 99.5% to 92.2% at p = 3, still much better than the 12.5% of random guessing, and the best plan found was still the optimum.

**Why only 3 qubits on hardware?** The Open Plan gives 600 s of QPU time per 28 days, and the 3-qubit circuit has only 4-12 two-qubit gates, so it survives the noise. The 9 and 18 qubit versions need hundreds of gates; we simulated those, including with an IBM noise model.

**Does QAOA beat random guessing?** Per sample, yes (Q3: 58% vs 12.5%; Q9: 4.9% vs 0.2%). But on the small problems, thousands of random samples also contain the optimum.

**Why not the top-1 plan accuracy for Q9 and Q18?** The most likely QAOA sample is often not the optimum there. We report top-1 and best-of-N separately so nothing is hidden.

**How do you know the result is right?** One shared evaluator scores everything, 177 automated tests pass, and the key numbers ($10,925 and $9,175) are verified by hand in `docs/manual_verification.md`.

**What did Qiskit do?** QuadraticProgram, SparsePauliOp, `qaoa_ansatz`, Aer Estimator and Sampler, noise models from FakeFez, `generate_preset_pass_manager`, Runtime `QiskitRuntimeService` and `Sampler` with dynamical decoupling and twirling. See the table in the README.
