import { Link } from "react-router-dom";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";

import { useApi } from "../hooks/useApi";
import { api, CATEGORY_COLORS, fmtPct } from "../services/api";
import {
  CategoryTag, DirectionPill, ErrorBox, Loading, QualityNote, StatCard,
} from "../components/ui";

function MoverList({ title, skills, tone }) {
  const border = tone === "up" ? "border-emerald-200" : "border-red-200";
  return (
    <div className={`rounded-xl border ${border} bg-white p-4`}>
      <h3 className="text-sm font-semibold">{title}</h3>
      {skills.length === 0 ? (
        <p className="mt-3 text-xs text-slate-500">No skills met the threshold.</p>
      ) : (
        <ul className="mt-3 space-y-2">
          {skills.map((s) => (
            <li key={s.skill} className="flex items-center justify-between gap-2">
              <Link
                to={`/forecast?skill=${encodeURIComponent(s.skill)}`}
                className="truncate text-sm font-medium hover:underline"
              >
                {s.skill}
              </Link>
              <div className="flex shrink-0 items-center gap-2">
                <span className="text-xs tabular-nums text-slate-500">
                  {fmtPct(s.previous_pct)} → {fmtPct(s.recent_pct)}
                </span>
                <DirectionPill direction={s.direction} change={s.change_pts} />
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Dashboard() {
  const { data, error, loading } = useApi(() => api.summary(), []);

  if (loading) return <Loading label="Loading dashboard…" />;
  if (error) return <ErrorBox message={error} />;

  const q = data.data_quality;
  const m = data.model_quality;
  const chart = data.top_skills.map((s) => ({
    skill: s.skill,
    pct: s.overall_pct,
    category: s.category,
  }));

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold">Market overview</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          Which technical skills employers asked for, and how that changed.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Job postings"
          value={data.total_postings.toLocaleString()}
          sub={`${data.date_range_start} → ${data.date_range_end}`}
        />
        <StatCard
          label="Skills tracked"
          value={data.skills_tracked}
          sub={`${data.categories} categories`}
        />
        <StatCard
          label="Extraction hit rate"
          value={fmtPct(data.extraction_hit_rate_pct)}
          sub={`vs ${fmtPct(data.baseline_hit_rate_pct)} for the dataset's own labels`}
          accent="text-emerald-700"
        />
        <StatCard
          label="Analysis-grade months"
          value={`${q.analysis_grade_months} / ${q.total_months}`}
          sub={`${q.analysis_start} → ${q.analysis_end}`}
        />
      </div>

      <QualityNote>
        <strong>Why {q.excluded_months} months are excluded.</strong>{" "}
        {q.exclusion_reason}
      </QualityNote>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold">Most demanded skills</h3>
        <p className="mb-3 text-xs text-slate-500">
          Mean share of job postings mentioning each skill, across the 21
          analysis-grade months.
        </p>
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={chart} margin={{ top: 4, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
            <XAxis
              dataKey="skill"
              tick={{ fontSize: 11, fill: "#64748b" }}
              interval={0}
              angle={-30}
              textAnchor="end"
              height={70}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#64748b" }}
              tickFormatter={(v) => `${v}%`}
            />
            <Tooltip
              formatter={(v) => [`${v.toFixed(2)}%`, "of postings"]}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
            />
            <Bar dataKey="pct" radius={[4, 4, 0, 0]}>
              {chart.map((entry) => (
                <Cell
                  key={entry.skill}
                  fill={CATEGORY_COLORS[entry.category] ?? "#2563eb"}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        <MoverList title="Rising skills" skills={data.rising_skills} tone="up" />
        <MoverList title="Declining skills" skills={data.declining_skills} tone="down" />
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold">Top 10 at a glance</h3>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs uppercase tracking-wide text-slate-500">
                <th className="py-2 pr-3 font-medium">Skill</th>
                <th className="py-2 pr-3 font-medium">Category</th>
                <th className="py-2 pr-3 text-right font-medium">Mean</th>
                <th className="py-2 pr-3 text-right font-medium">Peak</th>
                <th className="py-2 font-medium">Trend</th>
              </tr>
            </thead>
            <tbody>
              {data.top_skills.map((s) => (
                <tr key={s.skill} className="border-b border-slate-100 last:border-0">
                  <td className="py-2 pr-3 font-medium">
                    <Link
                      to={`/forecast?skill=${encodeURIComponent(s.skill)}`}
                      className="hover:underline"
                    >
                      {s.skill}
                    </Link>
                  </td>
                  <td className="py-2 pr-3">
                    <CategoryTag category={s.category} />
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums">
                    {fmtPct(s.overall_pct)}
                  </td>
                  <td className="py-2 pr-3 text-right tabular-nums text-slate-500">
                    {fmtPct(s.peak_pct)}
                  </td>
                  <td className="py-2">
                    <DirectionPill direction={s.direction} change={s.change_pts} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {m && (
        <QualityNote tone="blue">
          <strong>How much to trust the forecasts.</strong> {m.verdict}
        </QualityNote>
      )}
    </div>
  );
}
