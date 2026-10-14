import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { useApi } from "../hooks/useApi";
import { api, CATEGORY_COLORS, fmtPct } from "../services/api";
import {
  CategoryTag, DirectionPill, Empty, ErrorBox, Loading, PctBar,
} from "../components/ui";

const DIRECTIONS = ["all", "rising", "declining", "stable", "insufficient data"];

export default function SkillExplorer() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("all");
  const [direction, setDirection] = useState("all");
  const [sort, setSort] = useState("overall_pct");

  const cats = useApi(() => api.categories(), []);
  const skills = useApi(() => api.skills({ limit: 500, sort }), [sort]);

  const filtered = useMemo(() => {
    if (!skills.data) return [];
    return skills.data.filter((s) => {
      if (category !== "all" && s.category !== category) return false;
      if (direction !== "all" && s.direction !== direction) return false;
      if (query && !s.skill.toLowerCase().includes(query.toLowerCase())) return false;
      return true;
    });
  }, [skills.data, category, direction, query]);

  const maxPct = useMemo(
    () => Math.max(...filtered.map((s) => s.overall_pct), 1),
    [filtered]
  );

  if (skills.loading || cats.loading) return <Loading label="Loading skills…" />;
  if (skills.error) return <ErrorBox message={skills.error} />;
  if (cats.error) return <ErrorBox message={cats.error} />;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">Skill explorer</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          All {skills.data.length} tracked skills. Filter by category, direction or name.
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex-1 min-w-[180px]">
            <span className="block text-xs font-medium text-slate-500">Search</span>
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="e.g. python"
              className="mt-1 w-full rounded-md border border-slate-300 px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
            />
          </label>

          <label>
            <span className="block text-xs font-medium text-slate-500">Category</span>
            <select
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
            >
              <option value="all">All categories</option>
              {cats.data.map((c) => (
                <option key={c.category} value={c.category}>
                  {c.category} ({c.skill_count})
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="block text-xs font-medium text-slate-500">Direction</span>
            <select
              value={direction}
              onChange={(e) => setDirection(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
            >
              {DIRECTIONS.map((d) => (
                <option key={d} value={d}>
                  {d === "all" ? "Any direction" : d}
                </option>
              ))}
            </select>
          </label>

          <label>
            <span className="block text-xs font-medium text-slate-500">Sort by</span>
            <select
              value={sort}
              onChange={(e) => setSort(e.target.value)}
              className="mt-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
            >
              <option value="overall_pct">Demand</option>
              <option value="change_pts">Biggest change</option>
              <option value="skill">Name</option>
            </select>
          </label>
        </div>

        <p className="mt-2 text-xs text-slate-500">
          Showing {filtered.length} of {skills.data.length} skills
        </p>
      </div>

      {filtered.length === 0 ? (
        <Empty message="No skills match these filters." />
      ) : (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="px-3 py-2 font-medium">Skill</th>
                <th className="px-3 py-2 font-medium">Category</th>
                <th className="px-3 py-2 font-medium" style={{ minWidth: 160 }}>
                  Mean demand
                </th>
                <th className="px-3 py-2 text-right font-medium">Mentions</th>
                <th className="px-3 py-2 font-medium">Trend</th>
                <th className="px-3 py-2 text-right font-medium">Volatility</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => (
                <tr key={s.skill} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="px-3 py-2 font-medium">
                    <Link
                      to={`/forecast?skill=${encodeURIComponent(s.skill)}`}
                      className="hover:underline"
                    >
                      {s.skill}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <CategoryTag category={s.category} />
                  </td>
                  <td className="px-3 py-2">
                    <PctBar
                      value={s.overall_pct}
                      max={maxPct}
                      color={CATEGORY_COLORS[s.category] ?? "#2563eb"}
                    />
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-600">
                    {s.total_mentions.toLocaleString()}
                  </td>
                  <td className="px-3 py-2">
                    <DirectionPill direction={s.direction} change={s.change_pts} />
                  </td>
                  <td
                    className="px-3 py-2 text-right tabular-nums text-slate-500"
                    title="Standard deviation of monthly demand. Higher means a noisier, less reliable trend."
                  >
                    {s.volatility.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-xs text-slate-500">
        <strong>Volatility</strong> is the standard deviation of monthly demand.
        Two skills can show the same change while one moved steadily and the
        other bounced around — the steady one's trend is more trustworthy.
        <strong> “too sparse”</strong> means fewer than 100 total mentions, which
        cannot support a claim about direction.
      </p>
    </div>
  );
}
