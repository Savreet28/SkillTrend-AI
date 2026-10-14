"""Test the skill extractor against hand-written cases.

Each case has an expected set of skills. This is a REAL test: it fails
loudly when the extractor is wrong. Running this before touching 58,000
real descriptions means bugs show up where they're easy to diagnose.

The tricky cases matter most -- punctuation-heavy names, and skill names
that are also ordinary English words.
"""

from skill_extractor import SkillExtractor

CASES: list[tuple[str, set[str]]] = [
    (
        "Looking for a data analyst with strong SQL and Python skills. "
        "Experience with Tableau or Power BI required.",
        {"SQL", "Python", "Tableau", "Power BI"},
    ),
    (
        # Alias normalisation: three spellings, one canonical answer
        "Must know PowerBI, power-bi and Power BI.",
        {"Power BI"},
    ),
    (
        # Punctuation-heavy names that regex \b would mangle
        "Proficient in C++, C#, CI/CD pipelines and scikit-learn.",
        {"C++", "C#", "CI/CD", "Scikit-learn"},
    ),
    (
        # AMBIGUITY: "excel at" is the verb, not the product
        "The ideal candidate will excel at communication and go above "
        "and beyond for the team.",
        set(),
    ),
    (
        # ...but real Excel still matches
        "Advanced Excel skills including pivot tables required.",
        {"Microsoft Excel"},
    ),
    (
        # AMBIGUITY: bare "go" must never match; golang must
        "Experience with Golang and Kubernetes is a plus.",
        {"Go", "Kubernetes"},
    ),
    (
        # GenAI terms the dataset's own labels cannot see
        "Build RAG applications using LangChain, OpenAI and vector databases. "
        "Prompt engineering experience with LLMs preferred.",
        {"RAG", "LangChain", "OpenAI", "Vector Database", "Prompt Engineering", "LLM"},
    ),
    (
        # Aliases across categories
        "Stack: postgres, mongo, no-sql, amazon web services, pyspark.",
        {"PostgreSQL", "MongoDB", "NoSQL", "AWS", "Apache Spark"},
    ),
]


def main() -> None:
    extractor = SkillExtractor()
    print(f"Loaded {extractor.skill_count} skills\n")

    failures = 0

    for i, (text, expected) in enumerate(CASES, start=1):
        actual = extractor.extract(text)

        if actual == expected:
            print(f"PASS  case {i}")
            continue

        failures += 1
        print(f"FAIL  case {i}")
        print(f"      text:     {text[:70]}...")
        print(f"      expected: {sorted(expected)}")
        print(f"      actual:   {sorted(actual)}")
        print(f"      missing:  {sorted(expected - actual)}")
        print(f"      extra:    {sorted(actual - expected)}")

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")

    if failures:
        raise SystemExit(f"{failures} case(s) failed")


if __name__ == "__main__":
    main()