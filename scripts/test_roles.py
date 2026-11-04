"""Test the role classifier against hand-written titles.

The ordering of the rules in roles.py is the whole trick, and ordering
bugs are silent: every ML Engineer quietly becomes a Software Engineer
and nothing crashes. These cases pin the order down.
"""

from roles import classify_role, explain

CASES: list[tuple[str, str]] = [
    # --- ordering: specific must beat general -------------------------
    ("Senior Machine Learning Engineer", "Machine Learning Engineer"),
    ("MLOps Engineer", "Machine Learning Engineer"),
    ("AI Engineer, Platform", "Machine Learning Engineer"),
    ("Data Engineer (Spark)", "Data Engineer"),
    ("Analytics Engineer", "Data Engineer"),
    ("Site Reliability Engineer", "DevOps / SRE"),
    ("Cloud Infrastructure Engineer", "DevOps / SRE"),
    ("Security Engineer, AppSec", "Security Engineer"),
    ("QA Automation Engineer", "QA / Test Engineer"),
    # ...and only then the catch-all
    ("Software Engineer II", "Software Engineer"),
    ("Senior Backend Engineer", "Software Engineer"),
    ("Full Stack Developer", "Software Engineer"),
    ("iOS Developer", "Software Engineer"),

    # --- data roles are distinguished from each other ------------------
    ("Data Scientist", "Data Scientist"),
    ("Staff Data Scientist, Growth", "Data Scientist"),
    ("Data Analyst", "Data Analyst"),
    ("Business Intelligence Analyst", "Data Analyst"),
    ("BI Developer", "Data Analyst"),

    # --- product ------------------------------------------------------
    ("Senior Product Manager", "Product Manager"),
    ("Technical Program Manager", "Product Manager"),

    # --- non-tech must NOT be forced into a bucket --------------------
    ("Group Fitness Instructor", "Other"),
    ("Freelance Writer", "Other"),
    ("Strategic Account Executive", "Other"),
    ("Head of Marketing", "Other"),

    # --- edge cases ---------------------------------------------------
    ("", "Other"),
    (None, "Other"),
]


def main() -> None:
    failures = 0

    for i, (title, expected) in enumerate(CASES, start=1):
        actual = classify_role(title)
        if actual == expected:
            print(f"PASS  case {i:>2}  {str(title)[:40]:<40} -> {actual}")
            continue

        failures += 1
        print(f"FAIL  case {i:>2}  {str(title)[:40]}")
        print(f"      expected: {expected}")
        print(f"      actual:   {actual}")
        print(f"      why:      {explain(title or '')}")

    print(f"\n{len(CASES) - failures}/{len(CASES)} passed")
    if failures:
        raise SystemExit(f"{failures} case(s) failed")


if __name__ == "__main__":
    main()
