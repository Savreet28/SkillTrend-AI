import { useState } from "react";
import {
  CartesianGrid, Legend, Line, LineChart, ReferenceArea,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { useApi } from "../hooks/useApi";
import { api, fmtMonth, SERIES_COLORS } from "../services/api";
import { ErrorBox, Loading, QualityNote } from "../components/ui";

const PRESETS = [
  ["Python", "R", "SQL"],
  ["Power BI", "Tableau", "Looker"],
  ["AWS", "Azure", "GCP"],
  ["Snowflake", "Databricks", "Redshift"],
  ["Apache Spark", "Hadoop", "dbt"],
];

const MAX_SKILLS = 6;

export default function Compare() {
  const [selected, setSelected] = useState(["Python", "R", "SQL"]);
  const [smooth, setSmooth] = useState(false);

  const all = useApi(() => api.skills({ limit: 500, sort: "overall_pct" }), []);
  const trends = useApi(() => api.trends(selected), [selected.join("|")]);

  function toggle(skill) {
    setSelected((cur) =>
      cur.includes(skill)
        ? cur.filter((s) => s !== skill)
        : cur.length >= MAX_SKILLS
          ? cur
          : [...cur, skill]
    );
  }

  if (all.loading) return <Loading label="Loading skills…" />;
  if (all.error) return <ErrorBox message={all.error} />;

  // Pivot the per-skill series into one row per month for Recharts.
  let rows = [];
  let firstExcluded = null;
  if (trends.data && trends.data.length) {
    const months = trends.data[0].points.map((p) => p.month);
    rows = months.map((month, i) => {
      const row = { month, label: fmtMonth(month) };
      for (const series of trends.data) {
        const pt = series.points[i];
        row[series.skill] = smooth ? pt.rolling_3m : pt.demand_pct;
        row.__grade = pt.is_analysis_grade;
      }
      return row;
    });
    const idx = trends.data[0].points.findIndex((p) => !p.is_analysis_grade);
    if (idx > 0) firstExcluded = months[idx];
  }

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">Compare skills</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          Pick up to {MAX_SKILLS} skills and see their demand side by side.
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs font-medium text-slate-500">Quick picks:</span>
          {PRESETS.map((preset) => (
            <button
              key={preset.join()}
              onClick={() => setSelected(preset)}
              className="rounded-full border border-slate-300 px-2.5 py-1 text-xs font-medium text-slate-700 hover:border-slate-900 hover:bg-slate-50"
            >
              {preset.join(" vs ")}
            </button>
          ))}
          <label className="ml-auto flex items-center gap-1.5 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={smooth}
              onChange={(e) => setSmooth(e.target.checked)}
            />
            3-month average
          </label>
        </div>

        <div className="mt-3 max-h-36 overflow-y-auto border-t border-slate-100 pt-3">
          <div className="flex flex-wrap gap-1.5">
            {all.data.slice(0, 90).map((s) => {
              const on = selected.includes(s.skill);
              const full = !on && selected.length >= MAX_SKILLS;
              return (
                <button
                  key={s.skill}
                  onClick={() => toggle(s.skill)}
                  disabled={full}
                  className={`rounded-md border px-2 py-0.5 text-xs transition-colors ${
                    on
                      ? "border-slate-900 bg-slate-900 text-white"
                      : full
                        ? "cursor-not-allowed border-slate-200 text-slate-300"
                        : "border-slate-200 text-slate-600 hover:border-slate-400"
                  }`}
                >
                  {s.skill}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {selected.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 p-10 text-center text-sm text-slate-500">
          Select at least one skill above.
        </div>
      ) : trends.loading ? (
        <Loading label="Loading series…" />
      ) : trends.error ? (
        <ErrorBox message={trends.error} />
      ) : (
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold">
            {smooth ? "3-month rolling average" : "Monthly demand"}
          </h3>
          <p className="mb-3 text-xs text-slate-500">
            % of that month's job postings mentioning the skill.
          </p>
          <ResponsiveContainer width="100%" height={380}>
            <LineChart data={rows} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748b" }} minTickGap={16} />
              <YAxis
                tick={{ fontSize: 11, fill: "#64748b" }}
                tickFormatter={(v) => `${v}%`}
              />
              <Tooltip
                formatter={(v, name) => [v == null ? "—" : `${v.toFixed(2)}%`, name]}
                contentStyle={{ fontSize: 12, borderRadius: 8 }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {firstExcluded && (
                <ReferenceArea
                  x1={fmtMonth(firstExcluded)}
                  x2={rows[rows.length - 1].label}
                  fill="#ef4444"
                  fillOpacity={0.06}
                  label={{ value: "excluded", fontSize: 10, fill: "#b91c1c" }}
                />
              )}
              {trends.data.map((series, i) => (
                <Line
                  key={series.skill}
                  type="monotone"
                  dataKey={series.skill}
                  stroke={SERIES_COLORS[i % SERIES_COLORS.length]}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>

          <div className="mt-3">
            <QualityNote>
              The shaded region to the right is excluded from all trend
              calculations. From late 2024 the scraper captured truncated job
              descriptions (median ~1,600 characters vs ~3,000 before), so fewer
              skills were found per posting and <em>every</em> line drops at
              once. That is a measurement artifact, not a change in demand — it
              is drawn so you can see it, not used in any conclusion.
            </QualityNote>
          </div>
        </div>
      )}
    </div>
  );
}
