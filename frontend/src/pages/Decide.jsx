import { useState } from "react";
import { Link } from "react-router-dom";

import { useApi } from "../hooks/useApi";
import { api, fmtPct } from "../services/api";
import { ErrorBox, Loading, QualityNote, StatCard } from "../components/ui";

const PRESETS = [
  { label: "Analyst starter", skills: ["Microsoft Excel", "SQL", "Tableau", "Power BI"] },
  { label: "Modern data stack", skills: ["Python", "SQL", "Snowflake", "dbt"] },
  { label: "Legacy analytics", skills: ["SAS", "SPSS", "Microsoft Excel", "Oracle"] },
  { label: "ML leaning", skills: ["Python", "TensorFlow", "PyTorch", "SQL"] },
];

const SEVERITY = {
  high: "border-red-200 bg-red-50",
  medium: "border-amber-200 bg-amber-50",
  low: "border-emerald-200 bg-emerald-50",
};

const KIND_LABEL = {
  redundant: "Redundant",
  missing: "Missing",
  declining: "Declining",
  solid: "Looks good",
};

function RedundantEvidence({ evidence }) {
  return (
    <table className="mt-2 w-full text-xs">
      <thead>
        <tr className="text-left text-slate-500">
          <th className="py-1 pr-2 font-medium">Tool</th>
          <th className="py-1 pr-2 text-right font-medium">2022–24</th>
          <th className="py-1 pr-2 text-right font-medium">Now</th>
          <th className="py-1 pr-2 text-right font-medium">Change</th>
          <th className="py-1 font-medium">Verdict</th>
        </tr>
      </thead>
      <tbody>
        {evidence.map((e) => (
          <tr key={e.skill} className="border-t border-black/5">
            <td className="py-1 pr-2 font-medium">{e.skill}</td>
            <td className="py-1 pr-2 text-right tabular-nums">{fmtPct(e.historical_pct)}</td>
            <td className="py-1 pr-2 text-right tabular-nums">{fmtPct(e.current_pct)}</td>
            <td className="py-1 pr-2 text-right tabular-nums">
              {e.change_pts > 0 ? "+" : ""}{e.change_pts}p
            </td>
            <td className="py-1">
              <span
                className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${
                  e.verdict === "keep"
                    ? "bg-emerald-600 text-white"
                    : "bg-slate-200 text-slate-600"
                }`}
              >
                {e.verdict}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function MissingEvidence({ evidence }) {
  return (
    <ul className="mt-2 space-y-1 text-xs">
      {evidence.map((e) => (
        <li key={e.skill} className="flex flex-wrap items-baseline gap-x-2">
          <Link
            to={`/forecast?skill=${encodeURIComponent(e.skill)}`}
            className="font-medium hover:underline"
          >
            + {e.skill}
          </Link>
          <span className="text-slate-600">
            in <strong className="tabular-nums">{e.conditional_pct}%</strong> of
            postings that want {e.appears_with.join(", ")}
          </span>
          {e.direction === "rising" && (
            <span className="rounded bg-emerald-100 px-1 text-[10px] font-semibold text-emerald-700">
              rising {e.change_pts > 0 ? "+" : ""}{e.change_pts}p
            </span>
          )}
          {e.direction === "declining" && (
            <span className="rounded bg-red-100 px-1 text-[10px] font-semibold text-red-700">
              declining
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

function DecliningEvidence({ evidence }) {
  return (
    <ul className="mt-2 space-y-1 text-xs">
      {evidence.map((e) => (
        <li key={e.skill}>
          <strong>{e.skill}</strong>{" "}
          <span className="tabular-nums text-red-700">{e.change_pts}p</span>{" "}
          <span className="text-slate-600">
            — still {fmtPct(e.overall_pct)} of postings, so not useless; just a
            poor thing to start now.
          </span>
        </li>
      ))}
    </ul>
  );
}

function StackAnalyser({ allSkills }) {
  const [stack, setStack] = useState(["Python", "SQL", "Tableau", "Power BI"]);
  const [draft, setDraft] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  async function run(next = stack) {
    if (!next.length) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.analyseStack(next));
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  function add(skill) {
    if (!skill || stack.includes(skill)) return;
    const next = [...stack, skill];
    setStack(next);
    setDraft("");
    run(next);
  }

  function remove(skill) {
    const next = stack.filter((s) => s !== skill);
    setStack(next);
    next.length ? run(next) : setResult(null);
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold">Your stack</h3>
      <p className="text-xs text-slate-500">
        Add what you know or plan to learn. Every verdict shows the numbers
        behind it.
      </p>

      <div className="mt-3 flex flex-wrap gap-1.5">
        {stack.map((s) => (
          <button
            key={s}
            onClick={() => remove(s)}
            className="group flex items-center gap-1 rounded-md bg-slate-900 px-2 py-1 text-xs text-white"
            title="Remove"
          >
            {s}
            <span className="opacity-50 group-hover:opacity-100">×</span>
          </button>
        ))}
        {stack.length === 0 && (
          <span className="text-xs text-slate-400">No skills selected.</span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          list="all-skills"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && add(draft)}
          placeholder="Add a skill…"
          className="min-w-[160px] flex-1 rounded-md border border-slate-300 px-2.5 py-1.5 text-sm outline-none focus:border-slate-900"
        />
        <datalist id="all-skills">
          {allSkills.map((s) => (
            <option key={s.skill} value={s.skill} />
          ))}
        </datalist>
        <button
          onClick={() => add(draft)}
          className="rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
        >
          Add
        </button>
        <button
          onClick={() => run()}
          disabled={busy || !stack.length}
          className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:opacity-40"
        >
          {busy ? "Analysing…" : "Analyse"}
        </button>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-1.5">
        <span className="text-xs text-slate-500">Try:</span>
        {PRESETS.map((p) => (
          <button
            key={p.label}
            onClick={() => {
              setStack(p.skills);
              run(p.skills);
            }}
            className="rounded-full border border-slate-300 px-2.5 py-0.5 text-xs text-slate-700 hover:border-slate-900"
          >
            {p.label}
          </button>
        ))}
      </div>

      {error && (
        <div className="mt-3">
          <ErrorBox message={error} />
        </div>
      )}

      {result && !error && (
        <div className="mt-4 space-y-3">
          <p className="text-sm font-medium">{result.summary}</p>

          {result.unknown.length > 0 && (
            <p className="text-xs text-amber-700">
              Not recognised (not in the 120-skill dictionary):{" "}
              {result.unknown.join(", ")}
            </p>
          )}

          {result.verdicts.map((v, i) => (
            <div
              key={i}
              className={`rounded-lg border p-3 ${SEVERITY[v.severity] ?? SEVERITY.low}`}
            >
              <div className="flex flex-wrap items-baseline gap-2">
                <span className="rounded bg-black/10 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide">
                  {KIND_LABEL[v.kind] ?? v.kind}
                </span>
                <span className="text-sm font-semibold">{v.headline}</span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-slate-700">{v.detail}</p>

              {v.kind === "redundant" && <RedundantEvidence evidence={v.evidence} />}
              {v.kind === "missing" && <MissingEvidence evidence={v.evidence} />}
              {v.kind === "declining" && <DecliningEvidence evidence={v.evidence} />}
            </div>
          ))}

          {result.caveat && <QualityNote>{result.caveat}</QualityNote>}
        </div>
      )}
    </div>
  );
}

function Families({ families }) {
  const [open, setOpen] = useState(families[0]?.family ?? null);

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold">Tools that do the same job</h3>
      <p className="text-xs text-slate-500">
        Pick one per family. The recommendation is scored on historical demand,
        current demand, trend and how well it fits other stacks.
      </p>

      <div className="mt-3 space-y-1.5">
        {families.map((f) => {
          const isOpen = open === f.family;
          return (
            <div key={f.family} className="rounded-lg border border-slate-200">
              <button
                onClick={() => setOpen(isOpen ? null : f.family)}
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
              >
                <span className="text-sm font-medium">{f.family}</span>
                <span className="flex items-center gap-2">
                  <span className="rounded bg-emerald-600 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                    {f.recommended}
                  </span>
                  <span className="text-xs text-slate-400">
                    {f.members.length} options {isOpen ? "▴" : "▾"}
                  </span>
                </span>
              </button>

              {isOpen && (
                <div className="border-t border-slate-100 px-3 py-2">
                  <p className="text-xs italic text-slate-600">{f.reason}</p>
                  <p className="mt-1 text-xs font-medium">{f.rationale}</p>

                  <table className="mt-2 w-full text-xs">
                    <thead>
                      <tr className="text-left text-slate-500">
                        <th className="py-1 pr-2 font-medium">Tool</th>
                        <th className="py-1 pr-2 text-right font-medium">2022–24</th>
                        <th className="py-1 pr-2 text-right font-medium">Now</th>
                        <th className="py-1 pr-2 text-right font-medium">Change</th>
                        <th className="py-1 text-right font-medium">Score</th>
                      </tr>
                    </thead>
                    <tbody>
                      {f.members.map((m) => (
                        <tr
                          key={m.skill}
                          className={`border-t border-slate-100 ${
                            m.is_recommended ? "font-semibold text-emerald-800" : ""
                          }`}
                        >
                          <td className="py-1 pr-2">
                            {m.is_recommended && "★ "}
                            {m.skill}
                          </td>
                          <td className="py-1 pr-2 text-right tabular-nums">
                            {fmtPct(m.historical_pct)}
                          </td>
                          <td className="py-1 pr-2 text-right tabular-nums">
                            {fmtPct(m.current_pct)}
                          </td>
                          <td className="py-1 pr-2 text-right tabular-nums">
                            {m.change_pts > 0 ? "+" : ""}{m.change_pts}p
                          </td>
                          <td className="py-1 text-right tabular-nums">
                            {m.score.toFixed(2)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>

                  {f.warnings.length > 0 && (
                    <ul className="mt-2 space-y-0.5">
                      {f.warnings.map((w, i) => (
                        <li key={i} className="text-[11px] text-amber-800">
                          ⚠ {w}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function Decide() {
  const skills = useApi(() => api.skills({ limit: 500, sort: "overall_pct" }), []);
  const families = useApi(() => api.families(), []);

  if (skills.loading || families.loading) return <Loading label="Loading…" />;
  if (skills.error) return <ErrorBox message={skills.error} />;
  if (families.error) return <ErrorBox message={families.error} />;

  const totalAlternatives = families.data.reduce(
    (n, f) => n + f.members.length - 1, 0
  );

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">What should I learn?</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          Find what's redundant in your stack, what's missing, and what's on the
          way out.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label="Skills tracked" value={skills.data.length} />
        <StatCard label="Substitute families" value={families.data.length} />
        <StatCard
          label="Tools you can skip"
          value={totalAlternatives}
          sub="alternatives across all families"
          accent="text-emerald-700"
        />
        <StatCard
          label="Evidence base"
          value="58,276"
          sub="postings + live feed"
        />
      </div>

      <StackAnalyser allSkills={skills.data} />
      <Families families={families.data} />

      <QualityNote tone="blue">
        <strong>Why families are curated rather than learned.</strong> I tried
        to derive substitutes statistically and it failed, measurably: job ads
        write "Tableau, Power BI <em>or</em> Looker", so alternatives co-occur
        constantly. Known substitutes scored similarity 0.77 / lift 11.7 and
        known complements 0.93 / 23.5 — overlapping on every metric. So
        <strong> which tools are alternatives</strong> is declared by hand;
        <strong> which one to pick</strong> and <strong>what you're missing</strong>{" "}
        come entirely from the data. See <Link to="/about" className="underline">Method</Link>.
      </QualityNote>
    </div>
  );
}
