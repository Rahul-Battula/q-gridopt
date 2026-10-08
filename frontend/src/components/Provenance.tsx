import type { SolverResult } from "../types/api";
import { SourceBadge, fmtNum } from "./ui";

/** Where a result came from: source badge, backend, job id, shots, time, library versions. */
export function Provenance({ result }: { result: SolverResult }) {
  const p = result.provenance;
  return (
    <div className="space-y-1.5 text-xs">
      <SourceBadge source={result.source} jobId={p.job_id} />
      <div className="text-dim">{p.method}</div>
      <dl className="num grid grid-cols-[auto_1fr] gap-x-3 gap-y-0.5 text-dim">
        {p.backend && (<><dt className="text-faint">backend</dt><dd className="text-ink">{p.backend}</dd></>)}
        {p.job_id && (<><dt className="text-faint">job id</dt><dd className="text-ink">{p.job_id}</dd></>)}
        {p.shots != null && (<><dt className="text-faint">shots</dt><dd>{fmtNum(p.shots)}</dd></>)}
        <dt className="text-faint">time</dt><dd>{p.timestamp}</dd>
        {p.solve_time_s != null && (<><dt className="text-faint">solve</dt><dd>{p.solve_time_s.toFixed(3)} s</dd></>)}
        {Object.keys(p.library_versions).length > 0 && (
          <>
            <dt className="text-faint">versions</dt>
            <dd>{Object.entries(p.library_versions).map(([k, v]) => `${k} ${v}`).join(" · ")}</dd>
          </>
        )}
      </dl>
    </div>
  );
}
