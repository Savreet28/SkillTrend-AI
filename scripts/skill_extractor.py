"""Dictionary-based skill extraction using spaCy's PhraseMatcher.

Why PhraseMatcher instead of regex?
Regex word boundaries (\\b) break on the exact skill names we care about:
"C++", "C#", ".NET", "CI/CD", "Node.js". PhraseMatcher tokenises the
PATTERNS and the TEXT with the same tokeniser, so whatever spaCy does
to "c++" in a job description it also does to "c++" in our dictionary,
and they line up.

Why spacy.blank("en")?
It's the tokeniser with no neural network attached. No model download,
very fast, and completely deterministic -- the same input always gives
the same output, which means you can debug it.

Three rules keep the output honest:

1. LONGEST MATCH WINS (spacy.util.filter_spans).
   "no-sql" tokenises to no / - / sql, so a naive matcher reports both
   NoSQL *and* SQL. Keeping only the longest non-overlapping span means
   NoSQL wins and the spurious SQL is dropped. Same for "SQL Server",
   "Apache Spark" and "Azure Data Factory".

2. SOME CANONICAL NAMES ARE NEVER MATCHED ALONE (canonical_not_matched).
   "Go" is a real skill and also an extremely common English verb. Only
   its aliases count: golang, go programming, go language.

3. CONTEXT BLOCKLIST (blocked_next_tokens).
   "excel at communication" is the verb, not the product. If the token
   after a match is on that skill's blocklist, the match is discarded.

This module is imported by 03_extract.py and by test_extractor.py.
"""

from pathlib import Path

import spacy
import yaml
from spacy.matcher import PhraseMatcher
from spacy.tokens import Span
from spacy.util import filter_spans

ROOT = Path(__file__).resolve().parent.parent
SKILLS_FILE = ROOT / "skills" / "skills.yaml"


class SkillExtractor:
    """Finds canonical skill names in a piece of text."""

    def __init__(self, skills_file: Path = SKILLS_FILE) -> None:
        data = yaml.safe_load(skills_file.read_text())

        self.category_of: dict[str, str] = {}
        self.blocked_next: dict[str, set[str]] = {
            skill: set(tokens)
            for skill, tokens in (data.get("blocked_next_tokens") or {}).items()
        }
        skip_canonical = set(data.get("canonical_not_matched") or [])

        self.nlp = spacy.blank("en")
        # attr="LOWER" -> match on lowercase form, so casing never matters.
        self.matcher = PhraseMatcher(self.nlp.vocab, attr="LOWER")

        for category, skills in data["skills"].items():
            for canonical, aliases in (skills or {}).items():
                self.category_of[canonical] = category

                phrases = list(aliases or [])
                if canonical not in skip_canonical:
                    phrases.insert(0, canonical)
                if not phrases:
                    raise ValueError(f"{canonical!r} has no patterns to match")

                patterns = [self.nlp.make_doc(p.lower()) for p in phrases]
                # Registered under the CANONICAL name, so "powerbi",
                # "power-bi" and "Power BI" all come back as "Power BI".
                # That IS the normalisation step.
                self.matcher.add(canonical, patterns)

    @property
    def skill_count(self) -> int:
        return len(self.category_of)

    @property
    def categories(self) -> list[str]:
        return sorted(set(self.category_of.values()))

    def extract(self, text: str) -> set[str]:
        """Return the set of canonical skills mentioned in `text`."""
        return self._extract_from_doc(self.nlp(text))

    def extract_many(self, texts, batch_size: int = 200):
        """Extract from many texts efficiently. Yields one set per text."""
        for doc in self.nlp.pipe(texts, batch_size=batch_size):
            yield self._extract_from_doc(doc)

    def _extract_from_doc(self, doc) -> set[str]:
        spans: list[Span] = []

        for match_id, start, end in self.matcher(doc):
            skill = self.nlp.vocab.strings[match_id]

            # Rule 3: context blocklist. Applied BEFORE filter_spans so a
            # rejected span can never suppress a legitimate shorter one.
            blocked = self.blocked_next.get(skill)
            if blocked and end < len(doc) and doc[end].lower_ in blocked:
                continue

            spans.append(Span(doc, start, end, label=skill))

        # Rule 1: keep only the longest non-overlapping spans.
        return {span.label_ for span in filter_spans(spans)}


if __name__ == "__main__":
    ex = SkillExtractor()
    print(f"Loaded {ex.skill_count} skills across {len(ex.categories)} categories\n")
    for category in ex.categories:
        n = sum(1 for c in ex.category_of.values() if c == category)
        print(f"  {category:<32} {n:>3}")
