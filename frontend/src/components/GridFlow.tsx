import { useEffect, useMemo, useState, type ComponentType, type ReactNode } from "react";
import { C } from "../charts/theme";
import type { Scenario, SolverResult } from "../types/api";
import { IconBattery, IconBolt, IconCity, IconFlame, IconSun, IconWind } from "./icons";
import { Chip, fmtNum, fmtUsd } from "./ui";

export interface FlowVariant {
  id: string;
  label: string;
  result: SolverResult;
}

type IconType = ComponentType<{ size?: number; x?: number; y?: number; color?: string; strokeWidth?: number }>;

const OFF = "#C7CCE6";
const INK = "#14172E";

/** One pipe between two boxes: a coloured tube, moving dots for direction, an arrow head and a "MW" label on it. */
function Pipe({ x0, y0, x1, y1, mw, color, maxFlow }: {
  x0: number; y0: number; x1: number; y1: number; mw: number; color: string; maxFlow: number;
}) {
  const on = mw > 0.05;
  const w = 8 + Math.min(mw / maxFlow, 1) * 12;
  const dx = (x1 - x0) * 0.5;
  const d = `M${x0},${y0} C${x0 + dx},${y0} ${x1 - dx},${y1} ${x1},${y1}`;
  const mx = (x0 + x1) / 2;
  const my = (y0 + y1) / 2;
  const pill = on ? `${fmtNum(mw)} MW` : "0 MW";
  const pw = pill.length * 7.6 + 20;
  return (
    <g>
      <path d={d} fill="none" stroke={on ? color : OFF} strokeOpacity={on ? 0.28 : 0.6} strokeWidth={w + 8} strokeLinecap="round" />
      <path d={d} fill="none" stroke={on ? color : OFF} strokeWidth={on ? w : 4} strokeLinecap="round"
        strokeDasharray={on ? undefined : "2 9"} markerEnd={on ? "url(#arrow)" : undefined} />
      {on && <path d={d} fill="none" stroke="#fff" strokeOpacity={0.9} strokeWidth={3} className="flow" />}
      <g transform={`translate(${mx - pw / 2} ${my - 13})`}>
        <rect width={pw} height={26} rx={13} fill="#fff" stroke={on ? color : OFF} strokeWidth={1.5} />
        <text x={pw / 2} y={17.5} textAnchor="middle" fill={on ? INK : "#8B90AD"} fontSize={12.5} fontWeight={600} fontFamily="Plus Jakarta Sans, sans-serif">{pill}</text>
      </g>
    </g>
  );
}

/** A friendly box: big coloured icon, name, big number, one plain-English caption. */
function Tile({ x, y, w = 230, h = 100, color, Icon, name, value, caption, captionColor, children }: {
  x: number; y: number; w?: number; h?: number; color: string; Icon: IconType; name: string; value: string;
  caption: string; captionColor?: string; children?: ReactNode;
}) {
  return (
    <g transform={`translate(${x} ${y})`} filter="url(#lift)">
      <rect width={w} height={h} rx={20} fill="#fff" fillOpacity={0.92} stroke={color} strokeOpacity={0.45} strokeWidth={1.5} />
      <circle cx={46} cy={h / 2} r={29} fill={color} />
      <Icon x={30} y={h / 2 - 16} size={32} color="#fff" strokeWidth={1.8} />
      <text x={92} y={h / 2 - 16} fill="#565B7A" fontSize={13} fontWeight={600} fontFamily="Plus Jakarta Sans, sans-serif">{name}</text>
      <text x={92} y={h / 2 + 12} fill={INK} fontSize={28} fontWeight={700} fontFamily="Plus Jakarta Sans, sans-serif" letterSpacing="-0.02em">{value}</text>
      <text x={92} y={h / 2 + 31} fill={captionColor ?? "#565B7A"} fontSize={11.5} fontFamily="Plus Jakarta Sans, sans-serif">{caption}</text>
      {children}
    </g>
  );
}

type Hour = { solar: number; wind: number; gas: number; charge: number; discharge: number; unserved: number };

/** The story of the hour in one plain sentence. */
function story(name: string, x: Hour, curtailed: number): ReactNode {
  const b = (t: string, c: string) => <strong style={{ color: c }}>{t}</strong>;
  const parts: ReactNode[] = [];
  if (x.charge > 0.05) {
    parts.push(<>Sun and wind make <em>more</em> power than the city needs, so {b(`${fmtNum(x.charge)} MW`, C.battery)} is saved in the battery for later.</>);
  } else if (x.discharge > 0.05) {
    parts.push(<>The city needs more than sun and wind give, so the battery <em>gives back</em> {b(`${fmtNum(x.discharge)} MW`, C.battery)}{x.gas > 0.05 ? <> and gas only has to cover {b(`${fmtNum(x.gas)} MW`, C.gas)}</> : null}.</>);
  } else if (x.gas > 0.05) {
    parts.push(<>Sun and wind are not enough on their own, so the gas plant fills the gap with {b(`${fmtNum(x.gas)} MW`, C.gas)}. The battery rests.</>);
  } else {
    parts.push(<>Sun and wind cover everything. No gas needed.</>);
  }
  if (curtailed > 0.05) parts.push(<> {b(`${fmtNum(curtailed)} MW`, C.gas)} of clean power is wasted because nothing can use it.</>);
  if (x.unserved > 0.05) parts.push(<> {b(`${fmtNum(x.unserved)} MW`, C.bad)} of demand is not served.</>);
  return <><span className="font-semibold text-ink">{name}.</span> {parts}</>;
}

/** Hour-by-hour picture of the grid: who makes power, where it flows, who uses it. Pure display; numbers come from the backend. */
export function GridFlow({ scenario, variants }: { scenario: Scenario; variants: FlowVariant[] }) {
  const [variantId, setVariantId] = useState(variants[0]?.id);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(true);
  const variant = variants.find((v) => v.id === variantId) ?? variants[0];
  const periods = scenario.periods;

  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => setHour((h) => (h + 1) % periods.length), 4500);
    return () => clearInterval(timer);
  }, [playing, periods.length]);

  // one thickness scale for every hour and variant, so pipes are comparable across hours
  const maxFlow = useMemo(() => {
    let m = 1;
    for (const v of variants) {
      (v.result.schedule?.periods ?? []).forEach((x, i) => {
        m = Math.max(m, x.solar, x.wind, x.gas, x.charge, x.discharge, periods[i]?.demand ?? 0);
      });
    }
    return m;
  }, [variants, periods]);

  const schedule = variant?.result.schedule;
  const evaluation = variant?.result.evaluation;
  if (!variant || !schedule || !evaluation) return null;
  const p = periods[hour];
  const x = schedule.periods[hour];
  const m = evaluation.periods[hour];
  const unit = scenario.unit_commitment;
  const gasOn = unit ? (x.gas_on ?? x.gas > 0) : x.gas > 0.05;
  const cap = scenario.battery.capacity;
  const socEnd = m.soc_end;
  const soc = Math.min(socEnd / cap, 1);
  const curtailed = Math.max(p.solar - x.solar, 0) + Math.max(p.wind - x.wind, 0);
  const served = Math.max(p.demand - x.unserved, 0);
  const batteryMode = x.charge > 0.05 ? "charging" : x.discharge > 0.05 ? "discharging" : "resting";
  const batteryMw = x.charge > 0.05 ? x.charge : x.discharge;
  const supply = x.solar + x.wind + x.gas + x.discharge;

  return (
    <section className="card overflow-hidden rounded-lg">
      <header className="flex flex-wrap items-center justify-between gap-4 border-b border-line px-6 py-4">
        <div>
          <div className="label text-quantum">how the grid runs</div>
          <h2 className="display text-xl font-semibold">Who makes the power, and who uses it</h2>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          {variants.length > 1 && (
            <div className="flex rounded-lg tabs p-1">
              {variants.map((v) => (
                <button key={v.id} onClick={() => setVariantId(v.id)}
                  className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition ${v.id === variant.id ? "tab-active" : "text-dim hover:text-ink"}`}>
                  {v.label}
                </button>
              ))}
            </div>
          )}
          <div className="flex rounded-lg tabs p-1">
            {periods.map((q, i) => (
              <button key={q.name} onClick={() => { setHour(i); setPlaying(false); }}
                className={`rounded-md px-3.5 py-1.5 text-xs font-medium transition ${i === hour ? "tab-active" : "text-dim hover:text-ink"}`}>
                {q.name}
              </button>
            ))}
            <button onClick={() => setPlaying((v) => !v)} aria-label={playing ? "Pause" : "Play"}
              className="ml-1 grid h-7 w-7 place-items-center rounded-md text-dim transition hover:text-quantum">
              {playing ? (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><rect x="2" y="1.5" width="3" height="9" rx="1" /><rect x="7" y="1.5" width="3" height="9" rx="1" /></svg>
              ) : (
                <svg width="12" height="12" viewBox="0 0 12 12" fill="currentColor"><path d="M3 1.8v8.4L10 6 3 1.8Z" /></svg>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* the hour in one sentence */}
      <div className="mx-6 mt-5 flex items-start gap-3 rounded-lg border border-line bg-panel-2 px-4 py-3">
        <span className="accent-fill mt-0.5 grid h-8 w-8 shrink-0 place-items-center rounded-md text-white"><IconBolt size={17} /></span>
        <p className="text-[0.95rem] leading-relaxed text-dim">{story(p.name, x, curtailed)}</p>
      </div>

      <div className="px-3 pb-2 pt-3 sm:px-6">
        <svg viewBox="0 0 960 430" className="h-auto w-full" role="img"
          aria-label={`${p.name}: solar ${x.solar} MW, wind ${x.wind} MW, gas ${x.gas} MW flow through the grid to the city (${p.demand} MW); battery ${batteryMode}`}>
          <defs>
            <filter id="lift" x="-10%" y="-20%" width="120%" height="150%">
              <feDropShadow dx="0" dy="8" stdDeviation="9" floodColor="#3a2fa0" floodOpacity="0.14" />
            </filter>
            <marker id="arrow" viewBox="0 0 12 12" refX="9" refY="6" markerWidth="13" markerHeight="13" markerUnits="userSpaceOnUse" orient="auto">
              <path d="M1,1 L11,6 L1,11 Z" fill="context-stroke" />
            </marker>
            <linearGradient id="hubGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#5b3fd8" /><stop offset="1" stopColor="#0aa5c2" />
            </linearGradient>
          </defs>

          {/* column captions */}
          <text x={145} y={14} textAnchor="middle" fill="#8B90AD" fontSize={11} letterSpacing="0.12em" fontWeight={600} fontFamily="Plus Jakarta Sans, sans-serif">MAKES POWER</text>
          <text x={480} y={14} textAnchor="middle" fill="#8B90AD" fontSize={11} letterSpacing="0.12em" fontWeight={600} fontFamily="Plus Jakarta Sans, sans-serif">SHARES IT</text>
          <text x={815} y={14} textAnchor="middle" fill="#8B90AD" fontSize={11} letterSpacing="0.12em" fontWeight={600} fontFamily="Plus Jakarta Sans, sans-serif">USES / STORES IT</text>

          {/* pipes (drawn first so boxes sit on top) */}
          <Pipe x0={260} y0={85} x1={418} y1={165} mw={x.solar} color={C.solar} maxFlow={maxFlow} />
          <Pipe x0={260} y0={215} x1={418} y1={215} mw={x.wind} color={C.wind} maxFlow={maxFlow} />
          <Pipe x0={260} y0={345} x1={418} y1={265} mw={x.gas} color={C.gas} maxFlow={maxFlow} />
          <Pipe x0={542} y0={165} x1={698} y1={95} mw={served} color={C.quantum} maxFlow={maxFlow} />
          {batteryMode === "discharging" ? (
            <Pipe x0={698} y0={330} x1={542} y1={265} mw={batteryMw} color={C.battery} maxFlow={maxFlow} />
          ) : (
            <Pipe x0={542} y0={265} x1={698} y1={330} mw={batteryMode === "charging" ? batteryMw : 0} color={C.battery} maxFlow={maxFlow} />
          )}

          {/* makers */}
          <Tile x={30} y={35} color={C.solar} Icon={IconSun} name="Sun" value={`${fmtNum(x.solar)} MW`}
            caption={p.solar - x.solar > 0.05 ? `${fmtNum(p.solar - x.solar)} MW wasted` : "free and clean"}
            captionColor={p.solar - x.solar > 0.05 ? C.gas : undefined} />
          <Tile x={30} y={165} color={C.wind} Icon={IconWind} name="Wind" value={`${fmtNum(x.wind)} MW`}
            caption={p.wind - x.wind > 0.05 ? `${fmtNum(p.wind - x.wind)} MW wasted` : "free and clean"}
            captionColor={p.wind - x.wind > 0.05 ? C.gas : undefined} />
          <Tile x={30} y={295} color={C.gas} Icon={IconFlame} name={unit ? `Gas plant · ${gasOn ? "ON" : "OFF"}` : "Gas plant"} value={`${fmtNum(x.gas)} MW`}
            caption={x.gas > 0.05 ? "backup · costs money, makes CO₂" : unit && !gasOn ? "switched off" : "not needed"} />

          {/* the grid hub */}
          <g filter="url(#lift)">
            <rect x={420} y={105} width={120} height={220} rx={60} fill="url(#hubGrad)" />
            <IconBolt x={458} y={150} size={44} color="#fff" strokeWidth={1.8} />
            <text x={480} y={226} textAnchor="middle" fill="#fff" fontSize={14} fontWeight={700} fontFamily="Plus Jakarta Sans, sans-serif" letterSpacing="0.06em">THE GRID</text>
            <text x={480} y={252} textAnchor="middle" fill="#fff" fillOpacity={0.9} fontSize={20} fontWeight={700} fontFamily="Plus Jakarta Sans, sans-serif">{fmtNum(supply)} MW</text>
            <text x={480} y={270} textAnchor="middle" fill="#fff" fillOpacity={0.8} fontSize={11} fontFamily="Plus Jakarta Sans, sans-serif">being shared</text>
          </g>

          {/* users */}
          <Tile x={700} y={35} w={230} h={120} color={C.quantum} Icon={IconCity} name="City needs" value={`${fmtNum(p.demand)} MW`}
            caption={x.unserved > 0.05 ? `${fmtNum(x.unserved)} MW short!` : "all served ✓"} captionColor={x.unserved > 0.05 ? C.bad : C.ok}>
            <rect x={92} y={98} width={118} height={6} rx={3} fill="#E6E8F5" />
            <rect x={92} y={98} width={118 * Math.min(served / Math.max(p.demand, 1), 1)} height={6} rx={3} fill={x.unserved > 0.05 ? C.bad : C.ok} />
          </Tile>

          <Tile x={700} y={270} w={230} h={120} color={C.battery} Icon={IconBattery} name="Battery"
            value={batteryMode === "resting" ? "resting" : `${batteryMode === "charging" ? "+" : "−"}${fmtNum(batteryMw)} MW`}
            caption={`${batteryMode === "charging" ? "filling up" : batteryMode === "discharging" ? "giving back" : "idle"} · ${fmtNum(socEnd)} of ${fmtNum(cap)} MWh`}>
            <rect x={92} y={98} width={118} height={8} rx={4} fill="#E6E8F5" />
            <rect x={92} y={98} width={118 * soc} height={8} rx={4} fill={C.battery} style={{ transition: "width .8s ease" }} />
          </Tile>
        </svg>
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-line px-6 py-3.5">
        <Chip tone="ink">{p.name}</Chip>
        <Chip tone="ok">cost this hour {fmtUsd(m.total_cost)}</Chip>
        <Chip tone="gas">CO₂ {fmtNum(m.co2_tonnes, 1)} t</Chip>
        {m.curtailment > 0.05 && <Chip tone="warn">{fmtNum(m.curtailment)} MW wasted</Chip>}
        {scenario.reserve && <Chip tone={(m.reserve_shortfall_mw ?? 0) > 0.05 ? "bad" : "ok"}>reserve {(m.reserve_shortfall_mw ?? 0) > 0.05 ? `short ${fmtNum(m.reserve_shortfall_mw, 1)} MW` : "met"}</Chip>}
        <span className="ml-auto text-xs text-faint">moving dots show which way power flows · thicker pipe = more megawatts (MW) · {scenario.uncertainty ? "nominal forecast" : "forecast"}</span>
      </footer>
    </section>
  );
}
