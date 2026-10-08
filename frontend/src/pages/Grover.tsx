import { useQuery } from "@tanstack/react-query";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { ApiError, api } from "../api/client";
import { C, axisProps, legendProps, tooltipProps } from "../charts/theme";
import { IconGate } from "../components/icons";
import { ErrorBox, Loading, PageHeader, Panel, Stat, fmtNum } from "../components/ui";

const times = (v: number | null | undefined) => (v == null ? "—" : `${v >= 10 ? Math.round(v) : v.toFixed(2)}×`);

export function Grover() {
  const q = useQuery({ queryKey: ["grover"], queryFn: api.grover, retry: false });
  if (q.isLoading) return <Loading what="Loading Grover results" />;
  if (q.error instanceof ApiError && q.error.status === 404) {
    return (
      <Panel title="No Grover results yet">
        <p className="text-sm text-dim">Run the experiment from the project root, then reload this page:</p>
        <pre className="num mt-3 rounded-md border border-line bg-panel-2 px-4 py-3 text-xs text-ink">python backend\scripts\run_grover.py</pre>
      </Panel>
    );
  }
  if (q.error || !q.data) return <ErrorBox error={q.error} />;
  const g = q.data;
  const q18 = g.tiers.find((t) => t.tier === "Q18");
  const longest = g.chain[g.chain.length - 1];
  const chart = g.chain.map((r) => ({
    qubits: r.qubits,
    "Grover search": r.gas_queries_mean,
    "Classical blind search": r.random_unstructured_without_replacement_mean,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="06 · quantum speedup"
        title="Grover search:"
        accent="a real speedup, with limits"
        subtitle={`Measured over ${g.trials} independent runs per row. One query = one evaluation of the cost function. Where Grover wins, where it loses, and why, all on this page.`}
      />

      <Panel tag="idea" title="The idea in plain English">
        <div className="flex items-start gap-5">
          <span className="accent-fill grid h-14 w-14 shrink-0 place-items-center rounded-lg text-white"><IconGate size={30} /></span>
          <p className="max-w-4xl text-[0.95rem] leading-relaxed text-dim">
            Imagine every possible bit pattern as a door, with the cheapest battery plan behind one of them. A normal computer
            opens doors one by one. Grover's algorithm checks <strong className="text-ink">all doors at once</strong>, and each round makes the
            better doors a bit more likely to be found. With <em>N</em> doors it needs about <strong className="text-ink">√N</strong> rounds instead of
            about <em>N/2</em> tries. Our version keeps lowering the bar (&ldquo;find something cheaper than my best so far&rdquo;), so it
            never needs to be told the answer.
          </p>
        </div>
      </Panel>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Speedup, 18 qubits" value={times(q18?.speedup_vs_unstructured)} sub="vs searching every bit pattern blindly" tone="ok" />
        <Stat label={`Speedup, ${longest.qubits} qubits (grid with ${longest.hours} hours)`} value={times(longest.speedup_vs_unstructured)} sub="grows with problem size, about √N" tone="quantum" />
        <Stat label="Break-even size" value={g.first_hours_with_speedup ? `${g.first_hours_with_speedup} qubits` : "—"} sub="below this, plain guessing is as fast" tone="warn" />
        <Stat label="vs smart classical, 18 qubits" value={times(q18?.speedup_vs_structured)} sub="classical search that uses the problem structure wins" tone="bad" />
      </div>

      <Panel tag="chart" title="Queries needed to find the best plan (log scale)"
        right={<span className="num text-xs text-faint">fitted slope: Grover {g.exponent_gas.toFixed(2)} · classical {g.exponent_blind.toFixed(2)} (theory 0.5 · 1.0)</span>}>
        <ResponsiveContainer width="100%" height={320}>
          <LineChart data={chart} margin={{ top: 8, right: 16, left: 0, bottom: 16 }}>
            <CartesianGrid stroke={C.grid} strokeDasharray="3 6" />
            <XAxis dataKey="qubits" {...axisProps} label={{ value: "qubits (hours of the grid)", position: "insideBottom", offset: -8, fill: C.axis, fontSize: 11 }} />
            <YAxis {...axisProps} scale="log" domain={[1, "auto"]} width={56} tickFormatter={(v) => fmtNum(v)} />
            <Tooltip {...tooltipProps} formatter={(v) => `${fmtNum(Number(v), 1)} queries`} />
            <Legend {...legendProps} verticalAlign="top" />
            <Line dataKey="Classical blind search" stroke={C.classical} strokeWidth={2.5} dot={{ r: 3 }} />
            <Line dataKey="Grover search" stroke={C.quantum} strokeWidth={3} dot={{ r: 3.5 }} />
          </LineChart>
        </ResponsiveContainer>
        <p className="mt-2 text-xs text-faint">Both curves are averages of {g.trials} runs. The gap widens as the problem grows: that is the quadratic speedup.</p>
      </Panel>

      <Panel tag="table" title="The three project sizes">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="label text-left">
                {["Tier", "Qubits", "Bit patterns", "Valid plans", "Grover", "Blind search", "Speedup", "Smart classical", "Speedup", "Gates per round"].map((h) => (
                  <th key={h} className="pb-2.5 pr-4 font-medium">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {g.tiers.map((t) => (
                <tr key={t.tier} className="border-t border-line">
                  <td className="py-2.5 pr-4 font-semibold text-quantum">{t.tier}</td>
                  <td className="py-2.5 pr-4 num">{t.qubits}</td>
                  <td className="py-2.5 pr-4 num">{fmtNum(t.states)}</td>
                  <td className="py-2.5 pr-4 num">{fmtNum(t.valid_plans)}</td>
                  <td className="py-2.5 pr-4 num font-semibold text-quantum">{fmtNum(t.gas_queries_mean, 1)}</td>
                  <td className="py-2.5 pr-4 num">{fmtNum(t.random_unstructured_without_replacement_mean, 1)}</td>
                  <td className={`py-2.5 pr-4 num font-semibold ${(t.speedup_vs_unstructured ?? 0) >= 1 ? "text-ok" : "text-bad"}`}>{times(t.speedup_vs_unstructured)}</td>
                  <td className="py-2.5 pr-4 num">{fmtNum(t.classical_structured_mean, 1)}</td>
                  <td className={`py-2.5 pr-4 num font-semibold ${(t.speedup_vs_structured ?? 0) >= 1 ? "text-ok" : "text-bad"}`}>{times(t.speedup_vs_structured)}</td>
                  <td className="py-2.5 num text-dim">{t.one_iteration ? `${t.one_iteration.two_qubit_gates} two-qubit` : "not run"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-faint">
          Blind search = trying bit patterns at random. Smart classical = only trying the valid battery plans. Gates per round = one
          Grover round after transpiling for an IBM Heron chip (FakeFez).
        </p>
      </Panel>

      <Panel tag="honest" title="What this does and does not show" tone="warn">
        <ul className="grid gap-3 text-sm leading-relaxed text-dim md:grid-cols-2">
          <li><strong className="text-ink">It does show</strong> a real, measured quadratic speedup over unstructured search: {times(q18?.speedup_vs_unstructured)} at 18 qubits, and growing.</li>
          <li><strong className="text-ink">It does not show</strong> an advantage over the best classical solver. A classical search that only tries valid plans, or dynamic programming, needs far fewer queries.</li>
          <li><strong className="text-ink">Small problems:</strong> below the break-even size Grover is slower than guessing, because its constant factor is large.</li>
          <li><strong className="text-ink">Hardware:</strong> one Grover round needs about {g.tiers.find((t) => t.tier === "Q9")?.one_iteration?.two_qubit_gates ?? "1,000+"} two-qubit gates at 9 qubits, far more than today's noisy chips can run. Useful sizes need fault-tolerant machines.</li>
          <li className="md:col-span-2">
            The Grover state is computed with an exact formula that is checked against the real Qiskit circuit
            {g.qiskit_circuit_check ? ` (the circuit-driven search found the optimum in ${g.qiskit_circuit_check.found_optimum} of ${g.qiskit_circuit_check.runs} runs)` : ""}.
            No quantum computer produced these query counts.
          </li>
        </ul>
      </Panel>
    </div>
  );
}
