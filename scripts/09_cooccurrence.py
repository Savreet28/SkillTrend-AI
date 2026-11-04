"""Step 9: work out which skills are SUBSTITUTES and which are COMPLEMENTS.

Input:  data/processed/posting_skills.parquet
Output: data/processed/skill_graph.parquet      (every skill pair, scored)
        data/processed/skill_relations.json     (thresholds + validation report)

THE QUESTION
"Should I learn Power BI or Tableau?" is a different question from
"should I learn Docker or Kubernetes?". The first pair are alternatives
-- learning both is mostly wasted effort. The second pair are partners.
Raw co-occurrence cannot tell them apart, so we use two signals.

SIGNAL 1 -- CONTEXT SIMILARITY
Two skills are alike if they appear alongside the SAME OTHER SKILLS,
whether or not they appear with each other. Tableau and Power BI both
sit next to SQL, Excel and dashboards; neither sits next to Kubernetes.
Each skill gets a vector of PPMI scores against every other skill, and
similarity is the cosine between two such vectors.

PPMI (positive pointwise mutual information) is used instead of raw
counts because raw counts just rank everything by popularity -- SQL
appears beside everything, so it would dominate every vector and make
all skills look identical. PPMI measures how much MORE than chance two
skills appear together.

SIGNAL 2 -- DIRECT LIFT
How often A and B appear in the SAME posting, compared with chance.
  lift > 1  -> they attract: employers want both
  lift < 1  -> they repel: employers want one or the other

COMBINING THEM
  similar context + repel  = SUBSTITUTES   (pick one)
  similar context + attract = COMPLEMENTS  (learn both)
  dissimilar context        = unrelated

Crucially, when comparing A and B we exclude A and B from their own
context vectors. Otherwise a pair that co-occurs a lot scores as
"similar" purely because of each other, and every complement would be
misread as a substitute.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
IN_FILE = ROOT / "data" / "processed" / "posting_skills.parquet"
OUT_GRAPH = ROOT / "data" / "processed" / "skill_graph.parquet"
OUT_META = ROOT / "data" / "processed" / "skill_relations.json"

# Skills seen in fewer postings than this have noisy context vectors.
MIN_SUPPORT = 150

# Known pairs used to sanity-check the scoring. If these come out wrong,
# the thresholds or the method are wrong -- not the data.
VALIDATION = {
    "should be SUBSTITUTES": [
        ("Power BI", "Tableau"), ("Tableau", "Looker"), ("Power BI", "Qlik"),
        ("MySQL", "PostgreSQL"), ("AWS", "Azure"), ("Azure", "GCP"),
        ("TensorFlow", "PyTorch"), ("SAS", "SPSS"),
    ],
    "should be COMPLEMENTS": [
        ("Docker", "Kubernetes"), ("Python", "Pandas"), ("Python", "NumPy"),
        ("Apache Spark", "Hadoop"), ("ETL", "Data Warehouse"),
        ("Machine Learning", "Deep Learning"),
    ],
    "should be UNRELATED": [
        ("Tableau", "Kubernetes"), ("Microsoft Excel", "Docker"),
        ("PowerPoint", "Apache Kafka"),
    ],
}


def build_matrix(df: pd.DataFrame) -> tuple[np.ndarray, list[str]]:
    """Binary postings x skills matrix."""
    skills = sorted(df["skill"].unique())
    index = {s: i for i, s in enumerate(skills)}
    jobs = {j: i for i, j in enumerate(df["job_id"].unique())}

    m = np.zeros((len(jobs), len(skills)), dtype=np.float32)
    m[df["job_id"].map(jobs).to_numpy(), df["skill"].map(index).to_numpy()] = 1.0
    return m, skills


def ppmi(cooc: np.ndarray, counts: np.ndarray, n: int) -> np.ndarray:
    """Positive pointwise mutual information, diagonal zeroed."""
    expected = np.outer(counts, counts) / n
    with np.errstate(divide="ignore", invalid="ignore"):
        pmi = np.log(np.divide(cooc, expected, out=np.zeros_like(cooc),
                               where=expected > 0),
                     out=np.zeros_like(cooc), where=cooc > 0)
    out = np.maximum(pmi, 0.0)
    np.fill_diagonal(out, 0.0)
    return out


def masked_cosine(vectors: np.ndarray, i: int, j: int) -> float:
    """Cosine between rows i and j, with columns i and j removed.

    The mask is the important bit: without it, two skills that co-occur
    heavily look similar purely because of each other, and complements
    get misclassified as substitutes.
    """
    keep = np.ones(vectors.shape[1], dtype=bool)
    keep[[i, j]] = False
    a, b = vectors[i, keep], vectors[j, keep]
    na, nb = np.linalg.norm(a), np.linalg.norm(b)
    return float(a @ b / (na * nb)) if na and nb else 0.0


def main() -> None:
    if not IN_FILE.exists():
        raise SystemExit(f"Missing {IN_FILE}. Run 03_extract.py first.")

    df = pd.read_parquet(IN_FILE, columns=["job_id", "skill", "category"])
    category_of = dict(zip(df["skill"], df["category"]))

    support = df.groupby("skill")["job_id"].nunique()
    keep = support[support >= MIN_SUPPORT].index
    df = df[df["skill"].isin(keep)]

    matrix, skills = build_matrix(df)
    n_postings = matrix.shape[0]

    print("=" * 70)
    print("SKILL CO-OCCURRENCE")
    print("=" * 70)
    print(f"\nPostings   {n_postings:,}")
    print(f"Skills     {len(skills)}  (>= {MIN_SUPPORT} postings)")
    print(f"Dropped    {len(support) - len(skills)} too-rare skills")

    cooc = matrix.T @ matrix
    counts = np.diag(cooc).copy()
    vectors = ppmi(cooc, counts, n_postings)

    # ---- Score every pair ----------------------------------------------
    rows = []
    for i in range(len(skills)):
        for j in range(i + 1, len(skills)):
            both = cooc[i, j]
            expected = counts[i] * counts[j] / n_postings
            lift = float(both / expected) if expected > 0 else 0.0
            rows.append({
                "skill_a": skills[i],
                "skill_b": skills[j],
                "similarity": round(masked_cosine(vectors, i, j), 4),
                "lift": round(lift, 4),
                "both": int(both),
                "support_a": int(counts[i]),
                "support_b": int(counts[j]),
                # P(B | A): of people asked for A, how many are also asked for B
                "p_b_given_a": round(float(both / counts[i]) if counts[i] else 0, 4),
                "p_a_given_b": round(float(both / counts[j]) if counts[j] else 0, 4),
            })

    graph = pd.DataFrame(rows)
    graph["category_a"] = graph["skill_a"].map(category_of)
    graph["category_b"] = graph["skill_b"].map(category_of)

    # ---- Calibrate thresholds from the data ------------------------------
    # Rather than inventing numbers, take the similarity distribution and
    # call the top decile "similar context".
    sim_high = float(graph["similarity"].quantile(0.90))
    print(f"\nSimilarity distribution: median {graph['similarity'].median():.3f}  "
          f"p90 {sim_high:.3f}  max {graph['similarity'].max():.3f}")

    def classify(r) -> str:
        if r["similarity"] < sim_high:
            return "unrelated"
        return "substitute" if r["lift"] < 1.0 else "complement"

    graph["relation"] = graph.apply(classify, axis=1)
    graph.to_parquet(OUT_GRAPH, index=False)

    counts_by_rel = graph["relation"].value_counts()
    print("\nPairs by relation:")
    for rel in ("substitute", "complement", "unrelated"):
        print(f"  {rel:<12} {counts_by_rel.get(rel, 0):>6,}")

    # ---- Validate against known pairs -------------------------------------
    print("\n" + "=" * 70)
    print("VALIDATION — does this agree with what we already know?")
    print("=" * 70)

    lookup = {}
    for _, r in graph.iterrows():
        lookup[(r["skill_a"], r["skill_b"])] = r
        lookup[(r["skill_b"], r["skill_a"])] = r

    results = {}
    for expectation, pairs in VALIDATION.items():
        want = expectation.split()[-1].lower().rstrip("s")
        print(f"\n{expectation}")
        hits = total = 0
        for a, b in pairs:
            r = lookup.get((a, b))
            if r is None:
                print(f"  {a:<18} {b:<18}  (one of these was filtered out)")
                continue
            total += 1
            ok = r["relation"].startswith(want[:6])
            hits += ok
            mark = "OK " if ok else "XX "
            print(f"  {mark}{a:<18} {b:<18} sim {r['similarity']:.3f}  "
                  f"lift {r['lift']:.2f}  -> {r['relation']}")
        results[expectation] = f"{hits}/{total}"

    print("\nValidation summary:")
    for k, v in results.items():
        print(f"  {k:<26} {v}")

    # ---- What the engine actually recommends -----------------------------
    print("\n" + "-" * 70)
    print("STRONGEST SUBSTITUTE PAIRS  (learn one, not both)")
    print("-" * 70)
    subs = graph[graph["relation"] == "substitute"].nlargest(15, "similarity")
    for _, r in subs.iterrows():
        print(f"  {r['skill_a']:<20} vs {r['skill_b']:<20} "
              f"sim {r['similarity']:.3f}  lift {r['lift']:.2f}")

    print("\n" + "-" * 70)
    print("STRONGEST COMPLEMENT PAIRS  (learn both)")
    print("-" * 70)
    comps = graph[graph["relation"] == "complement"].nlargest(15, "similarity")
    for _, r in comps.iterrows():
        print(f"  {r['skill_a']:<20} +  {r['skill_b']:<20} "
              f"sim {r['similarity']:.3f}  lift {r['lift']:.2f}")

    OUT_META.write_text(json.dumps({
        "n_postings": int(n_postings),
        "n_skills": len(skills),
        "min_support": MIN_SUPPORT,
        "similarity_threshold": round(sim_high, 4),
        "validation": results,
        "pairs": int(len(graph)),
    }, indent=2))

    print(f"\nWrote {OUT_GRAPH.relative_to(ROOT)}  ({len(graph):,} pairs)")
    print(f"Wrote {OUT_META.relative_to(ROOT)}\n")


if __name__ == "__main__":
    main()
