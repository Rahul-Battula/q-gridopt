import { Suspense } from "react";
import { NavLink, Outlet, useLocation } from "react-router";
import { useHealth } from "../api/hooks";
import { IconAtom, IconBars, IconBloch, IconChip, IconGate, IconGrid, IconList } from "./icons";
import { useScenario } from "./ScenarioContext";
import { Chip, Loading } from "./ui";

const NAV = [
  { to: "/", label: "Grid & classical", hint: "scenario · optimum", Icon: IconGrid },
  { to: "/quantum", label: "Quantum workflow", hint: "QUBO · QAOA · circuits", Icon: IconBloch },
  { to: "/hardware", label: "IBM hardware", hint: "real QPU runs", Icon: IconChip },
  { to: "/runs", label: "Run log", hint: "every result, with provenance", Icon: IconList },
  { to: "/benchmark", label: "Benchmark", hint: "quantum vs classical", Icon: IconBars },
  { to: "/grover", label: "Grover search", hint: "the quantum speedup", Icon: IconGate },
];

function Logo() {
  return (
    <div className="flex items-center gap-3">
      <div className="relative grid h-10 w-10 place-items-center rounded-md accent-fill text-white ">
        <IconAtom size={24} strokeWidth={1.7} />
        <span className="absolute -right-1 -top-1 h-2.5 w-2.5 rounded-full bg-ok ring-2 ring-panel" />
      </div>
      <div className="leading-tight">
        <div className="display text-[1.15rem] font-semibold">Q-GridOpt</div>
        <div className="text-[0.7rem] text-dim">quantum grid scheduling</div>
      </div>
    </div>
  );
}

export function Layout() {
  const health = useHealth();
  const { presetId, custom } = useScenario();
  const location = useLocation();
  const online = health.data?.status === "ok";
  const current = NAV.find((n) => (n.to === "/" ? location.pathname === "/" : location.pathname.startsWith(n.to)));

  return (
    <div className="flex min-h-screen">
      <aside className="sticky top-0 hidden h-screen w-[18.5rem] shrink-0 flex-col gap-5 p-4 lg:flex">
        <div className="card flex h-full flex-col rounded-lg p-4">
          <div className="px-1.5 pb-5 pt-2">
            <Logo />
          </div>

          <div className="label px-2 pb-2">Workspace</div>
          <nav className="flex flex-col gap-1">
            {NAV.map(({ to, label, hint, Icon }, i) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `group relative flex items-center gap-3 rounded-md px-3 py-2.5 transition duration-200 ${
                    isActive
                      ? "tab-active"
                      : "text-dim hover:bg-panel-2 hover:text-ink"
                  }`
                }
              >
                {({ isActive }) => (
                  <>
                    {isActive && <span className="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-md accent-fill" />}
                    <span className={`grid h-8 w-8 place-items-center rounded-lg border transition ${isActive ? "border-quantum/40 bg-quantum/10 text-quantum" : "border-line bg-panel-2 group-hover:text-ink"}`}>
                      <Icon size={17} />
                    </span>
                    <span className="min-w-0 leading-tight">
                      <span className="block text-[0.87rem] font-medium">{label}</span>
                      <span className="block truncate text-[0.68rem] text-faint">{hint}</span>
                    </span>
                    <span className="num ml-auto text-[0.62rem] text-faint">0{i + 1}</span>
                  </>
                )}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto space-y-3 rounded-lg border border-line bg-panel-2 p-3.5 text-xs">
            <div className="label">System</div>
            <div className="flex items-center justify-between">
              <span className="text-dim">API</span>
              <Chip tone={online ? "ok" : "bad"} dot>{online ? "online" : health.isLoading ? "…" : "offline"}</Chip>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-dim">IBM Quantum</span>
              <Chip tone={health.data?.ibm_credentials_configured ? "ibm" : "ink"} dot>
                {health.data?.ibm_credentials_configured ? "key set" : "no key"}
              </Chip>
            </div>
            {health.data && (
              <div className="flex items-center justify-between">
                <span className="text-dim">Qiskit</span>
                <span className="num text-ink">{health.data.versions.qiskit}</span>
              </div>
            )}
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* compact top bar: breadcrumb + current scenario (nav collapses into it below lg) */}
        <div className="sticky top-0 z-20 border-b border-line bg-console ">
          <div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-5 py-3 sm:px-8">
            <div className="flex items-center gap-3 lg:hidden">
              <div className="grid h-8 w-8 place-items-center rounded-lg accent-fill text-white"><IconAtom size={19} strokeWidth={1.7} /></div>
              <span className="display font-semibold">Q-GridOpt</span>
            </div>
            <div className="hidden items-center gap-2 text-sm text-dim lg:flex">
              <span>Q-GridOpt</span>
              <span className="text-faint">/</span>
              <span className="text-ink">{current?.label ?? "Run details"}</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="hidden text-xs text-faint sm:inline">Scenario</span>
              <Chip tone="quantum" dot>{custom ? `${custom.name} (edited)` : presetId.replace("_", " ")}</Chip>
            </div>
          </div>
          <nav className="flex gap-1 overflow-x-auto px-5 pb-2 lg:hidden">
            {NAV.map(({ to, label, Icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === "/"}
                className={({ isActive }) =>
                  `flex shrink-0 items-center gap-2 rounded-md px-3 py-1.5 text-xs ${isActive ? "tab-active" : "text-dim"}`
                }
              >
                <Icon size={14} />
                {label}
              </NavLink>
            ))}
          </nav>
        </div>

        <main className="mx-auto w-full max-w-[1500px] min-w-0 flex-1 px-5 pb-16 pt-8 sm:px-8">
          <Suspense fallback={<Loading what="Loading page" />}>
            <Outlet />
          </Suspense>
        </main>
      </div>
    </div>
  );
}
