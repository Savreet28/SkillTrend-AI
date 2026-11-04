"""Classify a job title into a role family.

Same philosophy as the skill dictionary: ordered, rule-based, explainable.
You can point at exactly which pattern matched and why.

ORDER MATTERS, and that is the whole trick. "Senior Machine Learning
Engineer" contains the word "Engineer", so if Software Engineer were
checked first every ML role would be misfiled. The list runs from most
specific to least specific and stops at the first match.

Titles that match nothing become "Other" rather than being forced into
a bucket. A wrong label is worse than an honest unknown -- it would
quietly corrupt the role comparison.
"""

from __future__ import annotations

import re

# (role, [patterns]) in priority order. Patterns are lowercase substrings
# or regexes; they are matched against the lowercased title.
ROLE_RULES: list[tuple[str, list[str]]] = [
    ("Machine Learning Engineer", [
        r"\bml engineer", r"machine learning engineer", r"\bmlops",
        r"deep learning engineer", r"\bai engineer", r"applied scientist",
    ]),
    ("Data Scientist", [
        r"data scientist", r"\bdata science\b", r"research scientist",
        r"decision scientist",
    ]),
    ("Data Engineer", [
        r"data engineer", r"analytics engineer", r"\betl developer",
        r"big data engineer", r"data platform engineer", r"data architect",
    ]),
    ("Data Analyst", [
        r"data analyst", r"business intelligence", r"\bbi analyst",
        r"\bbi developer", r"analytics analyst", r"reporting analyst",
        r"business analyst", r"insights analyst",
    ]),
    ("DevOps / SRE", [
        r"\bdevops", r"site reliability", r"\bsre\b", r"platform engineer",
        r"infrastructure engineer", r"cloud engineer", r"systems engineer",
    ]),
    ("Security Engineer", [
        r"security engineer", r"\bappsec", r"information security",
        r"cyber ?security", r"security analyst",
    ]),
    ("QA / Test Engineer", [
        r"\bqa\b", r"quality assurance", r"test engineer",
        r"automation engineer", r"\bsdet\b",
    ]),
    ("Product Manager", [
        r"product manager", r"product owner", r"\bproduct lead",
        r"technical program manager", r"\btpm\b",
    ]),
    ("Software Engineer", [
        r"software engineer", r"software developer", r"\bbackend\b",
        r"\bback-end\b", r"\bfrontend\b", r"\bfront-end\b", r"full ?stack",
        r"\bweb developer", r"mobile (developer|engineer)",
        r"\bios (developer|engineer)", r"android (developer|engineer)",
        r"\bprogrammer\b", r"\bsoftware architect", r"\bdeveloper\b",
        r"\bengineer\b",          # deliberately last: the broadest catch
    ]),
]

COMPILED: list[tuple[str, list[re.Pattern]]] = [
    (role, [re.compile(p) for p in patterns]) for role, patterns in ROLE_RULES
]

ROLES: list[str] = [role for role, _ in ROLE_RULES] + ["Other"]


def classify_role(title: str | None) -> str:
    """Return the role family for a job title, or 'Other'."""
    if not title:
        return "Other"

    lowered = title.lower()
    for role, patterns in COMPILED:
        if any(p.search(lowered) for p in patterns):
            return role
    return "Other"


def explain(title: str) -> str:
    """Which pattern matched, for debugging. Used by the tests."""
    lowered = (title or "").lower()
    for role, patterns in COMPILED:
        for p in patterns:
            if p.search(lowered):
                return f"{role}  (matched /{p.pattern}/)"
    return "Other  (no pattern matched)"


if __name__ == "__main__":
    samples = [
        "Senior Machine Learning Engineer",
        "Staff Data Scientist, Growth",
        "Analytics Engineer (dbt)",
        "Business Intelligence Analyst II",
        "Site Reliability Engineer",
        "Senior Backend Engineer, Payments",
        "Full Stack Developer",
        "Technical Program Manager",
        "QA Automation Engineer",
        "Cyber Security Analyst",
        "Head of Marketing",
    ]
    width = max(len(s) for s in samples)
    for s in samples:
        print(f"{s:<{width}}  ->  {explain(s)}")
