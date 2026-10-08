import type { ReactNode } from "react";
import type { RunStatus, Source } from "../types/api";

export const fmtUsd = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : `$${v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
export const fmtPct = (v: number | null | undefined, digits = 1) => (v == null ? "—" : `${(v * 100).toFixed(digits)}%`);
export const fmtNum = (v: number | null | undefined, digits = 0) =>
  v == null ? "—" : v.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
export const fmtPath = (p: number[] | null | undefined) => (p ? `[${p.map((x) => Math.round(x)).join(", ")}]` : "—");
/** Gas unit commitment per hour, e.g. "on · on · off". */
export const fmtOnOff = (c: boolean[] | null | undefined) => (c ? c.map((x) => (x ? "on" : "off")).join(" · ") : "—");

type Tone = "ink" | "ok" | "warn" | "bad" | "quantum" | "gas" | "ibm" | "solar" | "wind" | "battery";

const TONE_TEXT: Record<Tone, string> = {
  ink: "text-ink",
  ok: "text-ok",
  warn: "text-warn",
  bad: "text-bad",
  quantum: "text-quantum",
  gas: "text-gas",
  ibm: "text-ibm",
  solar: "text-solar",
  wind: "text-wind",
  battery: "text-battery",
};
const TONE_BG: Record<Tone, string> = {
  ink: "bg-dim",
  ok: "bg-ok",
  warn: "bg-warn",
  bad: "bg-bad",
  quantum: "bg-quantum",
  gas: "bg-gas",
  ibm: "bg-ibm",
  solar: "bg-solar",
  wind: "bg-wind",
  battery: "bg-battery",
};

/** Page title block: small eyebrow, big display title (with an optional gradient part), subtitle, actions. */
export function PageHeader({
  eyebrow,
  title,
  accent,
  subtitle,
  actions,
}: {
  eyebrow: string;
  title: string;
  accent?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="flex flex-wrap items-end justify-between gap-5">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="num text-quantum">|</span>
          <span className="label text-quantum">{eyebrow}</span>
          <span className="num text-cyan">&#10217;</span>
        </div>
        <h1 className="display mt-2 text-[2rem] font-semibold leading-[1.1] sm:text-[2.4rem]">
          {title} {accent && <span className="quantum-text">{accent}</span>}
        </h1>
        {subtitle && <p className="mt-3 max-w-3xl text-[0.95rem] leading-relaxed text-dim">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-3">{actions}</div>}
    </header>
  );
}

export function Panel({
  title,
  tag,
  right,
  children,
  className = "",
  tone = "quantum",
}: {
  title?: string;
  tag?: string;
  right?: ReactNode;
  children: ReactNode;
  className?: string;
  tone?: Tone;
}) {
  return (
    <section className={`card overflow-hidden rounded-lg ${className}`}>
      {title && (
        <header className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <div className="flex items-center gap-3">
            {tag && (
              <span className={`num rounded-md border border-line bg-panel-2 px-2 py-0.5 text-[0.62rem] uppercase tracking-[0.08em] ${TONE_TEXT[tone]}`}>
                {tag}
              </span>
            )}
            <h2 className="display text-[0.98rem] font-medium text-ink">{title}</h2>
          </div>
          {right}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/** A KPI card: label, big number, supporting line. */
export function Stat({
  label,
  value,
  sub,
  tone = "ink",
  icon,
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: Tone;
  icon?: ReactNode;
}) {
  return (
    <div className="card group relative overflow-hidden rounded-lg px-4 py-3.5 transition duration-300  hover:border-line-bright">
      <div className="flex items-center justify-between gap-2">
        <div className="label">{label}</div>
        {icon && <span className={`${TONE_TEXT[tone]} opacity-80`}>{icon}</span>}
      </div>
      <div className={`display mt-2 text-[1.5rem] font-semibold leading-none tracking-tight ${TONE_TEXT[tone]}`}>{value}</div>
      {sub && <div className="mt-2 text-xs leading-snug text-dim">{sub}</div>}
    </div>
  );
}

/** Small tinted pill. */
export function Chip({ children, tone = "ink", dot = false }: { children: ReactNode; tone?: Tone; dot?: boolean }) {
  return (
    <span className={`num inline-flex items-center gap-1.5 rounded-md border border-line bg-panel-2 px-2.5 py-0.5 text-[0.68rem] ${TONE_TEXT[tone]}`}>
      {dot && <span className={`h-1.5 w-1.5 rounded-full ${TONE_BG[tone]}`} />}
      {children}
    </span>
  );
}

const SOURCE_STYLE: Record<Source, { label: string; tone: Tone; solid?: boolean }> = {
  classical_lp: { label: "Classical · LP (CBC)", tone: "ink" },
  classical_exact: { label: "Classical · exact", tone: "ink" },
  classical_no_battery: { label: "Classical · no battery", tone: "ink" },
  classical_annealing: { label: "Classical · annealing", tone: "ink" },
  aer_statevector: { label: "Qiskit Aer · ideal", tone: "quantum" },
  aer_noisy: { label: "Qiskit Aer · noisy", tone: "battery" },
  ibm_hardware: { label: "IBM Quantum QPU", tone: "ibm", solid: true },
};

export function SourceBadge({ source, jobId }: { source: Source; jobId?: string | null }) {
  const s = SOURCE_STYLE[source];
  if (s.solid) {
    return (
      <span className="num inline-flex items-center gap-2 rounded-md border border-ibm/60 bg-ibm/20 px-3 py-0.5 text-[0.7rem] text-ink ">
        <span className="h-1.5 w-1.5 rounded-full bg-ibm" />
        {s.label}
        {jobId && <span className="text-ibm">job {jobId}</span>}
      </span>
    );
  }
  return (
    <Chip tone={s.tone} dot>
      {s.label}
    </Chip>
  );
}

const STATUS_TONE: Record<RunStatus, Tone> = {
  queued: "ink",
  running: "quantum",
  submitted: "ibm",
  completed: "ok",
  failed: "bad",
};

export function StatusLight({ status, progress }: { status: RunStatus; progress?: string | null }) {
  const live = status === "running" || status === "submitted";
  const tone = STATUS_TONE[status];
  return (
    <span className="inline-flex items-center gap-2 text-xs">
      <span className={`relative inline-flex h-2 w-2 rounded-full ${TONE_BG[tone]} ${TONE_TEXT[tone]} ${live ? "animate-pulse-ring" : ""}`} />
      <span className={`num uppercase tracking-wider ${TONE_TEXT[tone]}`}>{status}</span>
      {progress && <span className="text-dim">· {progress}</span>}
    </span>
  );
}

export function Button({
  children,
  onClick,
  disabled,
  tone = "default",
  type = "button",
}: {
  children: ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  tone?: "default" | "primary" | "danger";
  type?: "button" | "submit";
}) {
  const cls = {
    default: "flat text-ink hover:border-line-bright hover:bg-panel-2",
    primary:
      "accent-fill border border-transparent font-semibold text-white  hover:brightness-110 hover:",
    danger:
      "border border-ibm/70 bg-ibm/25 font-semibold text-ink  hover:bg-ibm/40",
  }[tone];
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-2 rounded-md px-4 py-2 text-[0.78rem] font-medium tracking-wide transition duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none disabled:hover:brightness-100 ${cls}`}
    >
      {children}
    </button>
  );
}

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <div className="flex items-start gap-3 rounded-md border border-bad/40 bg-bad/10 px-4 py-3 text-sm text-bad">
      <span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-bad" />
      <span>{error instanceof Error ? error.message : String(error)}</span>
    </div>
  );
}

export function Loading({ what = "Loading" }: { what?: string }) {
  return (
    <div className="space-y-3 py-4" role="status">
      <div className="num flex items-center gap-2 text-sm text-dim">
        <span className="h-2 w-2 animate-pulse rounded-full bg-quantum" />
        {what}…
      </div>
      <div className="skeleton h-3 w-2/3" />
      <div className="skeleton h-3 w-1/2" />
    </div>
  );
}

export function Skeleton({ className = "h-24" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}
