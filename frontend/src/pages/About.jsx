import { useApi } from "../hooks/useApi";
import { api, fmtPct } from "../services/api";
import { ErrorBox, Loading } from "../components/ui";

function Section({ title, children }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h3 className="text-sm font-semibold">{title}</h3>
      <div className="mt-2 space-y-2 text-sm leading-relaxed text-slate-700">
        {children}
      </div>
    </section>
  );
}

export default function About() {
  const { data, error, loading } = useApi(() => api.summary(), []);

  if (loading) return <Loading />;
  if (error) return <ErrorBox message={error} />;

  const q = data.data_quality;
  const m = data.model_quality;

  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold">Method &amp; limitations</h2>
        <p className="mt-0.5 text-sm text-slate-600">
          What this project measures, how, and where it falls short.
        </p>
      </div>

      <Section title="The pipeline">
        <p>
          Six scripts run offline and write Parquet files; the API only reads
          them. Fitting 88 Prophet models cannot happen inside an HTTP request,
          so training and serving are separated — the same split real ML
          products use.
        </p>
        <ol className="ml-5 list-decimal space-y-1">
          <li><strong>Load</strong> — 61,953 raw postings, inspect schema and date coverage</li>
          <li><strong>Clean</strong> — parse dates, drop 3,177 duplicates and 500 stub descriptions → 58,276</li>
          <li><strong>Extract</strong> — spaCy PhraseMatcher over a 120-skill dictionary</li>
          <li><strong>Aggregate</strong> — skill × month, as a share of that month's postings</li>
          <li><strong>Trends</strong> — rolling averages, period comparison, direction classification</li>
          <li><strong>Forecast</strong> — Prophet, 6 months, backtested against a naive baseline</li>
        </ol>
      </Section>

      <Section title="Why percentages, not counts">
        <p>
          Monthly posting volume swings from 3,646 down to 272. Raw counts would
          show every skill collapsing in late 2024 when only the data collection
          changed. Measuring each skill as a share of that month's postings makes
          the numbers comparable across months.
        </p>
      </Section>

      <Section title="Skill extraction">
        <p>
          A curated dictionary of {data.skills_tracked} skills in{" "}
          {data.categories} categories, matched with spaCy's PhraseMatcher rather
          than regex — regex word boundaries break on <code>C++</code>,{" "}
          <code>C#</code> and <code>CI/CD</code>, whereas PhraseMatcher tokenises
          patterns and text the same way.
        </p>
        <p>Three rules keep it precise:</p>
        <ul className="ml-5 list-disc space-y-1">
          <li>
            <strong>Longest match wins.</strong> <code>no-sql</code> tokenises to
            no/-/sql, so a naive matcher reports both NoSQL and SQL.
          </li>
          <li>
            <strong>Some names never match alone.</strong> "Go" is also a common
            verb; only <code>golang</code> and <code>go programming</code> count.
            The dataset's own labels put Go at 3.77% — above Java — which is the
            verb, not the language.
          </li>
          <li>
            <strong>Context blocklists.</strong> "excel <em>at</em> communication"
            is rejected; "advanced Excel skills" is kept.
          </li>
        </ul>
        <p className="rounded-lg bg-emerald-50 p-2 text-emerald-900">
          Result: <strong>{fmtPct(data.extraction_hit_rate_pct)}</strong> of
          postings yielded at least one skill, against{" "}
          <strong>{fmtPct(data.baseline_hit_rate_pct)}</strong> for the labels
          shipped with the dataset — using a smaller vocabulary (120 terms vs
          134).
        </p>
      </Section>

      <Section title="The data-quality gate">
        <p>
          {q.analysis_grade_months} of {q.total_months} months are used for every
          trend and forecast ({q.analysis_start} → {q.analysis_end}).
        </p>
        <p>{q.exclusion_reason}</p>
        <p className="rounded-lg bg-amber-50 p-2 text-amber-900">
          Before this gate existed, the trend report showed 29 skills declining
          and only 2 rising. That looked like a dramatic finding. It was the
          scraper truncating text. The excluded months are still drawn on the
          comparison chart, shaded — hidden from conclusions, not from view.
        </p>
      </Section>

      {m && (
        <Section title="Does the forecasting model actually work?">
          <p>
            Each of the {m.skills_modelled} modelled skills was backtested: hold
            out the last 3 months, fit Prophet on the rest, and compare against
            carrying the last value forward.
          </p>
          <ul className="ml-5 list-disc">
            <li>Prophet mean absolute error: <strong>{m.mean_prophet_mae.toFixed(3)}</strong> percentage points</li>
            <li>Naive baseline: <strong>{m.mean_naive_mae.toFixed(3)}</strong></li>
            <li>Prophet won on <strong>{m.skills_beating_baseline} of {m.skills_modelled}</strong> skills ({m.pct_beating_baseline}%)</li>
          </ul>
          <p className="rounded-lg bg-blue-50 p-2 text-blue-900">
            {m.verdict}
          </p>
        </Section>
      )}

      <Section title="The role comparison (a second, separate data source)">
        <p>
          The Roles page does not use the Kaggle corpus at all. It pulls current
          postings each month from three free job-board APIs — Arbeitnow, Jobicy
          and Remotive — classifies each one into a role family from its title,
          and runs the same skill extractor over it.
        </p>
        <p>
          <strong>The two sources are never combined.</strong> The historical
          corpus is 58K US data-analyst ads from 2022–24; the live feed is a few
          thousand mostly-European, mostly-remote ads from this month. Averaging
          them would produce a number describing nobody.
        </p>
        <p className="rounded-lg bg-amber-50 p-2 text-amber-900">
          There are deliberately <strong>no role trends or forecasts</strong>.
          Job boards list only current openings, so the feed has no history — it
          accumulates one month at a time via a scheduled job. Drawing a trend
          through a single month would be inventing a result.
        </p>
        <p>
          <strong>Why APIs rather than a scraper:</strong> scraping Google job
          results means defeating CAPTCHAs, which is against their terms; Apify
          is paid; and a Selenium cron job breaks within weeks. These APIs are
          published by the job boards themselves, are free, and need no key.
        </p>
      </Section>

      <Section title="Limitations">
        <ul className="ml-5 list-disc space-y-1">
          <li>
            <strong>One role.</strong> Every posting is a data-analyst ad, so
            web and DevOps skills barely appear. This is not a picture of the
            whole tech market.
          </li>
          <li>
            <strong>One source.</strong> Scraped from Google job search results;
            whatever that misses, this misses.
          </li>
          <li>
            <strong>Scrape time, not posting time.</strong> The date is when the
            collector saw the ad, within a day or so of publication. Fine at
            monthly granularity, but not exact.
          </li>
          <li>
            <strong>A dictionary cannot find what it does not list.</strong> A
            skill absent from the 120 terms reads as 0% — indistinguishable from
            genuinely unwanted.
          </li>
          <li>
            <strong>Mentions are not requirements.</strong> "Python a plus" and
            "expert Python required" count identically.
          </li>
          <li>
            <strong>Forecasts are weak.</strong> 21 monthly points is very little
            history. The honest reading is a direction, not a number.
          </li>
          <li>
            <strong>Role profiles are small.</strong> Software Engineer has ~790
            postings behind it; Data Analyst has ~37. Roles under 100 are marked
            low confidence; under 30 they are dropped.
          </li>
          <li>
            <strong>~70% of the live feed is not tech.</strong> Arbeitnow is a
            general job board. Non-tech postings are classified "Other" and
            excluded from every role profile.
          </li>
        </ul>
      </Section>

      <Section title="Stack">
        <p>
          Python · pandas · spaCy · Prophet · FastAPI on the backend; React ·
          Vite · Tailwind · Recharts on the frontend. Everything is open source
          and runs locally — no paid services, no API keys.
        </p>
      </Section>
    </div>
  );
}
