import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Area, CartesianGrid, ComposedChart, Legend, Line, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { useApi } from "../hooks/useApi";
import { api, fmtMonth, fmtPct } from "../services/api";
import {
  CategoryTag, ErrorBox, Loading, QualityNote, StatCard,
} from "../components/ui";
import UploadPanel from "../components/UploadPanel";

export default function Forecast() {
  const [params, setParams] = useSearchParams();
  // The URL is the single source of truth for the selected skill. Mirroring
  // it into state needed an effect that called setState on every param
  // change, which cascades renders -- deriving it removes the effect.
  const skill = params.get("skill") || "Python";
  // null = the default corpus; otherwise an upload summary.
  const [dataset, setDataset] = useState(null);
  const [search, setSearch] = useState("");

  const all = useApi(() => api.skills({ limit: 500, sort: "overall_pct" }), []);
  const fc = useApi(
    () => api.forecast(skill, { dataset: dataset?.upload_id }),
    [skill, dataset?.upload_id]
  );

  function choose(next) {
    setParams({ skill: next });
  }

  if (all.loading) return <Loading label="Loading skills…" />;
  if (all.error) return <ErrorBox message={all.error} />;

  const visible = search
    ? all.data.filter((s) =>
        s.skill.toLowerCase().includes(search.toLowerCase()))
    : all.data;

  const rows =
    fc.data?.points.map((p) => ({
      label: fmtMonth(p.month),
      actual: p.actual,
      forecast: p.is_forecast ? p.yhat : null,
      // Recharts draws a stacked band: invisible base + visible height.
      bandBase: p.is_forecast ? p.yhat_lower : null,
      bandSize: p.is_forecast ? p.yhat_upper - p.yhat_lower : null,
      isForecast: p.is_forecast,
    })) ?? [];

  // Join history to forecast so the dashed line starts where the solid ends.
  const lastActualIdx = rows.map((r) => r.actual != null).lastIndexOf(true);
  if (lastActualIdx >= 0 && rows[lastActualIdx + 1]) {
    rows[lastActualIdx].forecast = rows[lastActualIdx].actual;
  }
  const boundary = lastActualIdx >= 0 ? rows[lastActualIdx].label : null;

  const m = fc.data?.metrics;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">Forecast</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          Observed history and a 6-month Prophet projection, with its
          backtested accuracy.
        </p>
      </div>

      <UploadPanel dataset={dataset} onDataset={setDataset} />

      <div className="rounded-xl border border-slate-200 bg-white p-3">
        <label className="block text-xs font-medium text-slate-500">Skill</label>
        <div className="mt-1 flex flex-wrap gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Filter skills…"
            className="w-40 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
          />
          <select
            value={skill}
            onChange={(e) => choose(e.target.value)}
            className="min-w-[200px] flex-1 rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
          >
            {visible.map((s) => (
              <option key={s.skill} value={s.skill}>
                {s.skill} — {fmtPct(s.overall_pct)}
              </option>
            ))}
          </select>
        </div>
        <p className="mt-1.5 text-xs text-slate-500">
          {dataset
            ? "Fitted on demand against your uploaded data."
            : "Only skills averaging ≥ 0.5% of postings are modelled. Anything rarer is too sparse for an honest forecast."}
        </p>
      </div>

      {fc.loading ? (
        <Loading label={`Loading forecast for ${skill}…`} />
      ) : fc.error ? (
        <ErrorBox message={fc.error} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="text-lg font-semibold">{fc.data.skill}</h3>
            <CategoryTag category={fc.data.category} />
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard
              label="Model error"
              value={`${m.prophet_mae.toFixed(2)}p`}
              sub="mean abs. error, 3-month holdout"
            />
            <StatCard
              label="Naive baseline error"
              value={`${m.naive_mae.toFixed(2)}p`}
              sub="assume next = last"
            />
            <StatCard
              label="Beats baseline?"
              value={m.beats_baseline ? "Yes" : "No"}
              sub={
                m.improvement_pct != null
                  ? `${m.improvement_pct > 0 ? "" : ""}${m.improvement_pct}% vs naive`
                  : "—"
              }
              accent={m.beats_baseline ? "text-emerald-700" : "text-red-700"}
            />
            <StatCard
              label="Observations"
              value={m.n_observations}
              sub="monthly data points"
            />
          </div>

          <div className="rounded-xl border border-slate-200 bg-white p-4">
            <ResponsiveContainer width="100%" height={380}>
              <ComposedChart data={rows} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 11, fill: "#64748b" }} minTickGap={16} />
                <YAxis
                  tick={{ fontSize: 11, fill: "#64748b" }}
                  tickFormatter={(v) => `${v}%`}
                />
                <Tooltip
                  formatter={(v, name) => {
                    if (v == null) return ["—", name];
                    if (name === "bandBase") return [null, null];
                    if (name === "bandSize") return [`${v.toFixed(2)}p wide`, "80% interval"];
                    return [`${v.toFixed(2)}%`, name === "actual" ? "Observed" : "Forecast"];
                  }}
                  contentStyle={{ fontSize: 12, borderRadius: 8 }}
                />
                <Legend
                  wrapperStyle={{ fontSize: 12 }}
                  payload={[
                    { value: "Observed", type: "line", color: "#2563eb" },
                    { value: "Forecast", type: "line", color: "#9333ea" },
                    { value: "80% interval", type: "rect", color: "#c4b5fd" },
                  ]}
                />

                <Area
                  dataKey="bandBase"
                  stackId="band"
                  stroke="none"
                  fill="transparent"
                  isAnimationActive={false}
                  legendType="none"
                />
                <Area
                  dataKey="bandSize"
                  stackId="band"
                  stroke="none"
                  fill="#c4b5fd"
                  fillOpacity={0.45}
                  isAnimationActive={false}
                  legendType="none"
                />

                {boundary && (
                  <ReferenceLine
                    x={boundary}
                    stroke="#94a3b8"
                    strokeDasharray="4 4"
                    label={{ value: "today", fontSize: 10, fill: "#64748b", position: "top" }}
                  />
                )}

                <Line
                  type="monotone"
                  dataKey="actual"
                  stroke="#2563eb"
                  strokeWidth={2.5}
                  dot={false}
                  connectNulls={false}
                  isAnimationActive={false}
                />
                <Line
                  type="monotone"
                  dataKey="forecast"
                  stroke="#9333ea"
                  strokeWidth={2.5}
                  strokeDasharray="6 4"
                  dot={{ r: 3, fill: "#9333ea" }}
                  connectNulls
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>

            <p className="mt-2 text-xs text-slate-500">
              <strong>Solid blue</strong> is observed history.{" "}
              <strong>Dashed purple</strong> is the model's projection, shaded
              with its 80% uncertainty interval. They are deliberately drawn
              differently — one is data, the other is a guess.
            </p>
          </div>

          <QualityNote tone={m.beats_baseline ? "blue" : "amber"}>
            <strong>Honest assessment.</strong> {fc.data.caveat}
          </QualityNote>

          <QualityNote>
            <strong>Why the model is kept simple.</strong> Yearly seasonality is
            switched off: 21 monthly observations is 1.75 annual cycles, and
            fitting a yearly pattern to less than two cycles means fitting noise.
            Prophet would happily produce confident-looking seasonal wiggles with
            nothing behind them.
          </QualityNote>
        </>
      )}
    </div>
  );
}
