import { NavLink, Outlet } from "react-router-dom";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/skills", label: "Skill Explorer" },
  { to: "/compare", label: "Compare" },
  { to: "/forecast", label: "Forecast" },
  { to: "/about", label: "Method" },
];

export default function Layout() {
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <div className="mr-2">
            <h1 className="text-base font-bold leading-tight">SkillTrend AI</h1>
            <p className="text-[11px] leading-tight text-slate-500">
              Skill demand in data-analyst roles
            </p>
          </div>

          <nav className="flex flex-wrap gap-1">
            {NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-slate-900 text-white"
                      : "text-slate-600 hover:bg-slate-100"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>

      <main className="mx-auto max-w-6xl px-4 py-6">
        <Outlet />
      </main>

      <footer className="mx-auto max-w-6xl px-4 pb-10 pt-4 text-xs text-slate-400">
        58,276 job postings · Nov 2022 – Apr 2025 · trends and forecasts use
        21 analysis-grade months (Nov 2022 – Jul 2024)
      </footer>
    </div>
  );
}
