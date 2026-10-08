/** The quantum pipeline, step by step, labelled with the Qiskit component and backend file each step uses. */
type Phase = "encode" | "train" | "run" | "decode";

const PHASES: Record<Phase, { label: string; text: string; bg: string; ring: string; dot: string }> = {
  encode: { label: "Encode", text: "text-battery", bg: "bg-battery/15", ring: "border-battery/40", dot: "bg-battery" },
  train: { label: "Train", text: "text-quantum", bg: "bg-quantum/15", ring: "border-quantum/40", dot: "bg-quantum" },
  run: { label: "Run", text: "text-ibm", bg: "bg-ibm/15", ring: "border-ibm/40", dot: "bg-ibm" },
  decode: { label: "Decode", text: "text-ok", bg: "bg-ok/15", ring: "border-ok/40", dot: "bg-ok" },
};

const STEPS: { title: string; plain: string; qiskit: string; file: string; phase: Phase }[] = [
  {
    title: "Battery plan → QUBO",
    plain: "One yes/no variable per (hour, battery level). Energy = $ cost + penalty for invalid plans.",
    qiskit: "qiskit_optimization.QuadraticProgram",
    file: "quantum/qubo.py",
    phase: "encode",
  },
  {
    title: "QUBO → Ising Hamiltonian",
    plain: "Rewrite 0/1 variables as ±1 spins (x = (1 − Z)/2) to get an energy operator.",
    qiskit: "qiskit.quantum_info.SparsePauliOp",
    file: "quantum/ising.py",
    phase: "encode",
  },
  {
    title: "QAOA circuit",
    plain: "Alternate cost layers (angle γ) and mixer layers (angle β), p times.",
    qiskit: "qiskit.circuit.library.qaoa_ansatz",
    file: "quantum/qaoa.py",
    phase: "encode",
  },
  {
    title: "Train angles",
    plain: "Search γ, β that make cheap plans likely, using exact expectation values.",
    qiskit: "qiskit_aer.primitives.EstimatorV2 + SciPy COBYLA",
    file: "quantum/qaoa.py",
    phase: "train",
  },
  {
    title: "Sample (ideal)",
    plain: "Run the trained circuit thousands of times and read off battery plans.",
    qiskit: "qiskit_aer AerSimulator + SamplerV2",
    file: "quantum/aer_runner.py",
    phase: "run",
  },
  {
    title: "Fit to an IBM chip",
    plain: "Rewrite into the chip's native gates and qubit layout (adds SWAPs only if needed).",
    qiskit: "qiskit.transpiler.generate_preset_pass_manager",
    file: "quantum/transpile.py",
    phase: "run",
  },
  {
    title: "Sample with device noise",
    plain: "Same circuit and angles, with a real IBM Heron chip's error rates.",
    qiskit: "AerSimulator.from_backend(FakeFez)",
    file: "quantum/simulate.py",
    phase: "run",
  },
  {
    title: "IBM Quantum hardware",
    plain: "Same circuit on a real QPU (only with your approval).",
    qiskit: "qiskit_ibm_runtime QiskitRuntimeService + Sampler",
    file: "quantum/ibm_runner.py",
    phase: "run",
  },
  {
    title: "Decode & score",
    plain: "Bitstring → battery plan → merit-order schedule → shared evaluator.",
    qiskit: "Qiskit counts → decoder",
    file: "quantum/decoder.py",
    phase: "decode",
  },
];

export function Pipeline() {
  return (
    <section className="card rounded-lg p-5 sm:p-6">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="label text-quantum">the pipeline</div>
          <h2 className="display text-xl font-semibold">Nine Qiskit steps, from battery plan to qubits and back</h2>
        </div>
        <div className="flex flex-wrap gap-3 text-xs">
          {(Object.keys(PHASES) as Phase[]).map((k) => (
            <span key={k} className="inline-flex items-center gap-1.5 text-dim">
              <span className={`h-2 w-2 rounded-full ${PHASES[k].dot}`} />
              {PHASES[k].label}
            </span>
          ))}
        </div>
      </div>
      <ol className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {STEPS.map((s, i) => {
          const ph = PHASES[s.phase];
          return (
            <li key={s.title}
              className="group relative flex min-w-0 flex-col rounded-lg border border-line bg-panel-2 p-4 transition duration-300  hover:border-line-bright hover:bg-panel-2">
              <div className="flex items-center gap-3">
                <span className={`display grid h-8 w-8 shrink-0 place-items-center rounded-md border text-sm font-semibold ${ph.bg} ${ph.ring} ${ph.text}`}>
                  {i + 1}
                </span>
                <div className="min-w-0">
                  <div className="font-medium leading-tight text-ink">{s.title}</div>
                  <div className={`num text-[0.62rem] uppercase tracking-[0.14em] ${ph.text}`}>{ph.label}</div>
                </div>
              </div>
              <p className="mt-3 flex-1 text-[0.82rem] leading-relaxed text-dim">{s.plain}</p>
              <div className="mt-3 space-y-1 rounded-md border border-line bg-panel-2 px-3 py-2">
                <div className="num text-[0.63rem] leading-snug tracking-tight text-quantum [overflow-wrap:anywhere]">{s.qiskit}</div>
                <div className="num text-[0.62rem] text-faint">backend/app/{s.file}</div>
              </div>
              {i < STEPS.length - 1 && (
                <span aria-hidden className="absolute -right-2.5 top-1/2 z-10 hidden h-5 w-5 -translate-y-1/2 place-items-center rounded-md border border-line bg-panel text-[0.6rem] text-faint xl:grid">
                  {(i + 1) % 3 === 0 ? "↓" : "→"}
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
