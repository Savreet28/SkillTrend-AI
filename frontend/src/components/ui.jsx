/** Small shared presentational pieces used across every page. */

import { CATEGORY_COLORS, fmtPct } from "../services/api";

export function Loading({ label = "Loading…" }) {
  return (
    <div className="flex items-center gap-3 py-16 justify-center text-slate-500">
      <span className="h-4 w-4 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
      {label}
    </div>
  );
}

export function ErrorBox({ message }) {
  return (
    <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
      <p className="font-semibold">Something went wrong</p>
      <p className="mt-1">{message}</p>
      <p className="mt-2 text-red-600">
        Check that the backend is running:{" "}
        <code className="rounded bg-red-100 px-1">
          cd backend && uvicorn app.main:app --reload
        </code>
      </p>
    </div>
  );
}

export function Empty({ message }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
      {message}
    </div>
  );
}

export function StatCard({ label, value, sub, accent = "text-slate-900" }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </p>
      <p className={`mt-1 text-2xl font-bold tabular-nums ${accent}`}>{value}</p>
      {sub && <p className="mt-0.5 text-xs text-slate-500">{sub}</p>}
    </div>
  );
}

export function CategoryTag({ category }) {
  const color = CATEGORY_COLORS[category] ?? "#64748b";
  return (
    <span
      className="inline-block rounded px-1.5 py-0.5 text-[11px] font-medium"
      style={{ color, backgroundColor: `${color}1a` }}
    >
      {category}
    </span>
  );
}

export function DirectionPill({ direction, change }) {
  const styles = {
    rising: "bg-emerald-50 text-emerald-700 border-emerald-200",
    declining: "bg-red-50 text-red-700 border-red-200",
    stable: "bg-slate-50 text-slate-600 border-slate-200",
    "insufficient data": "bg-amber-50 text-amber-700 border-amber-200",
  };
  const arrow = { rising: "▲", declining: "▼", stable: "—" }[direction] ?? "?";
  const label = direction === "insufficient data" ? "too sparse" : direction;

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium ${
        styles[direction] ?? styles.stable
      }`}
    >
      <span>{arrow}</span>
      {label}
      {change !== null && change !== undefined && direction !== "insufficient data" && (
        <span className="tabular-nums">
          {change > 0 ? "+" : ""}
          {change.toFixed(2)}p
        </span>
      )}
    </span>
  );
}

/** Honest-labelling banner. Used wherever excluded months could mislead. */
export function QualityNote({ children, tone = "amber" }) {
  const tones = {
    amber: "border-amber-200 bg-amber-50 text-amber-900",
    blue: "border-blue-200 bg-blue-50 text-blue-900",
  };
  return (
    <div className={`rounded-lg border p-3 text-xs leading-relaxed ${tones[tone]}`}>
      {children}
    </div>
  );
}

export function PctBar({ value, max, color = "#2563eb" }) {
  const width = max > 0 ? Math.max((value / max) * 100, 1) : 0;
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
        <div
          className="h-full rounded-full"
          style={{ width: `${width}%`, backgroundColor: color }}
        />
      </div>
      <span className="w-14 text-right text-xs tabular-nums text-slate-600">
        {fmtPct(value, 1)}
      </span>
    </div>
  );
}
