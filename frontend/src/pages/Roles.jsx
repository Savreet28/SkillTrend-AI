import { useState } from "react";
import {
  Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { useApi } from "../hooks/useApi";
import { api, fmtPct, ROLE_COLORS } from "../services/api";
import {
  CategoryTag, Empty, ErrorBox, Loading, QualityNote, StatCard,
} from "../components/ui";

/** Blue intensity scaled to the value — makes the grid readable at a glance. */
function heatStyle(pct, max) {
  if (pct <= 0) return { color: "#cbd5e1" };
  const t = Math.min(pct / Math.max(max, 1), 1);
  return {
    backgroundColor: `rgba(37, 99, 235, ${0.07 + t * 0.62})`,
    color: t > 0.55 ? "#fff" : "#1e293b",
    fontWeight: t > 0.3 ? 600 : 400,
  };
}

function Matrix({ rows }) {
  if (!rows?.length) return <Empty message="No matrix data." />;
  const roles = rows[0].cells.map((c) => c.role);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr>
            <th className="sticky left-0 bg-white px-2 py-2 text-left font-medium text-slate-500">
              Skill
            </th>
            {roles.map((r) => (
              <th
                key={r}
                className="px-1 py-2 text-center align-bottom font-medium text-slate-600"
                style={{ minWidth: 62 }}
              >
                <span className="block leading-tight">{r.replace(" / ", " / ")}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const max = Math.max(...row.cells.map((c) => c.demand_pct));
            return (
              <tr key={row.skill}>
                <td className="sticky left-0 whitespace-nowrap bg-white px-2 py-1 font-medium">
                  {row.skill}
                </td>
                {row.cells.map((c) => (
                  <td
                    key={c.role}
                    className="px-1 py-1 text-center tabular-nums"
                    style={heatStyle(c.demand_pct, max)}
                    title={`${row.skill} — ${c.role}: ${c.demand_pct}%`}
                  >
                    {c.demand_pct > 0 ? c.demand_pct.toFixed(0) : "·"}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function Roles() {
  const [selected, setSelected] = useState("Software Engineer");
  const [sort, setSort] = useState("lift");

  const status = useApi(() => api.liveStatus(), []);
  const roles = useApi(() => api.roles(0), []);
  const matrix = useApi(() => api.roleMatrix({ limit: 16 }), []);
  const detail = useApi(
    () => api.role(selected, { sort, top: 12 }),
    [selected, sort]
  );

  if (status.loading) return <Loading label="Checking the live feed…" />;
  if (status.error) return <ErrorBox message={status.error} />;

  if (!status.data.available) {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-bold">Role comparison</h2>
        <QualityNote>
          <strong>The live feed has not been fetched yet.</strong> Run{" "}
          <code className="rounded bg-amber-100 px-1">
            python scripts/07_fetch_live.py
          </code>{" "}
          then{" "}
          <code className="rounded bg-amber-100 px-1">
            python scripts/08_roles.py
          </code>{" "}
          and reload. Everything else in the dashboard works without it.
        </QualityNote>
      </div>
    );
  }

  const s = status.data;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold">Role comparison</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          Do software engineers really use Python differently from data analysts?
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Live postings"
          value={s.live_postings.toLocaleString()}
          sub={`${Object.keys(s.sources).length} job boards`}
        />
        <StatCard
          label="Tech-role postings"
          value={s.tech_postings.toLocaleString()}
          sub={`${s.roles.length} role families`}
        />
        <StatCard
          label="Skill hit rate"
          value={fmtPct(s.hit_rate_pct)}
          sub="postings with ≥ 1 skill"
        />
        <StatCard
          label="Months collected"
          value={s.months_collected}
          sub="grows with each monthly fetch"
        />
      </div>

      <QualityNote>
        <strong>This page uses a different data source.</strong> {s.caveat}
      </QualityNote>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h3 className="text-sm font-semibold">Same skill, different roles</h3>
        <p className="mb-3 text-xs text-slate-500">
          Each number is the % of <em>that role's</em> postings mentioning the
          skill. Read <strong>across a row</strong> to compare roles. Darker = higher.
        </p>
        {matrix.loading ? (
          <Loading />
        ) : matrix.error ? (
          <ErrorBox message={matrix.error} />
        ) : (
          <Matrix rows={matrix.data} />
        )}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="text-sm font-semibold">One role in detail</h3>
          <div className="flex items-center gap-1 rounded-lg bg-slate-100 p-0.5">
            <button
              onClick={() => setSort("demand_pct")}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                sort === "demand_pct" ? "bg-white shadow-sm" : "text-slate-600"
              }`}
            >
              Most common
            </button>
            <button
              onClick={() => setSort("lift")}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                sort === "lift" ? "bg-white shadow-sm" : "text-slate-600"
              }`}
            >
              Most distinctive
            </button>
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {roles.data?.map((r) => (
            <button
              key={r.role}
              onClick={() => setSelected(r.role)}
              className={`rounded-md border px-2.5 py-1 text-xs transition-colors ${
                selected === r.role
                  ? "border-slate-900 bg-slate-900 text-white"
                  : "border-slate-200 text-slate-600 hover:border-slate-400"
              }`}
            >
              {r.role}
              <span className="ml-1.5 opacity-60">{r.n_postings}</span>
            </button>
          ))}
        </div>

        <p className="mt-2 text-xs text-slate-500">
          {sort === "lift" ? (
            <>
              <strong>Most distinctive</strong> plots how far above the
              all-role average each skill sits, in percentage points. Every role
              wants Python; only data roles want Tableau. Hover for the raw share.
            </>
          ) : (
            <>
              <strong>Most common</strong> ranks by raw share. Useful, but the
              top of the list tends to look similar for every role.
            </>
          )}
        </p>

        {detail.loading ? (
          <Loading />
        ) : detail.error ? (
          <ErrorBox message={detail.error} />
        ) : (
          <>
            {!detail.data.is_confident && (
              <div className="mt-3">
                <QualityNote>
                  <strong>Low confidence.</strong> Only{" "}
                  {detail.data.n_postings} postings behind this role so far.
                  One unusual employer moves these numbers noticeably. It will
                  firm up as the monthly fetches accumulate.
                </QualityNote>
              </div>
            )}

            <ResponsiveContainer width="100%" height={330}>
              <BarChart
                data={detail.data.top_skills}
                layout="vertical"
                margin={{ top: 8, right: 24, bottom: 4, left: 90 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickFormatter={(v) => (sort === "lift" ? `${v > 0 ? "+" : ""}${v}p` : `${v}%`)}
                />
                <YAxis
                  type="category"
                  dataKey="skill"
                  tick={{ fontSize: 11, fill: "#334155" }}
                  width={88}
                />
                <Tooltip
                  formatter={(_v, _n, p) => [
                    `${p.payload.demand_pct.toFixed(1)}% of postings · ` +
                      `${p.payload.lift > 0 ? "+" : ""}${p.payload.lift.toFixed(1)}p vs ` +
                      `the all-role average`,
                    p.payload.category,
                  ]}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                />
                {/* Plot the SAME field the API sorted by, otherwise the bars
                    come back in lift order but are drawn at demand_pct length
                    and the chart looks unsorted and broken. */}
                <Bar
                  dataKey={sort === "lift" ? "lift" : "demand_pct"}
                  radius={[0, 4, 4, 0]}
                  isAnimationActive={false}
                >
                  {detail.data.top_skills.map((d) => (
                    <Cell
                      key={d.skill}
                      fill={ROLE_COLORS[detail.data.role] ?? "#2563eb"}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>

            <div className="mt-2 flex flex-wrap gap-1.5">
              {[...new Set(detail.data.top_skills.map((d) => d.category))].map((c) => (
                <CategoryTag key={c} category={c} />
              ))}
            </div>
          </>
        )}
      </div>

      <QualityNote tone="blue">
        <strong>Why there are no role trends or forecasts here.</strong> Job
        boards list only current openings, so this feed began collecting in{" "}
        {s.months_collected === 1 ? "this month" : `the last ${s.months_collected} months`}{" "}
        and has no history yet. It accumulates one month at a time; once
        several months have built up, role trends become possible. Drawing a
        trend line through a single month would be inventing a result.
      </QualityNote>
    </div>
  );
}
