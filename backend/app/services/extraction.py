"""Give the API access to the pipeline's skill extractor.

The extractor lives in scripts/ because that is where it is developed and
tested. Rather than duplicating it here (two copies would drift, and the
dictionary is the heart of the project), the backend imports that one.

scripts/ ships with the repo and is only a few KB, so this costs nothing
at deploy time.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[3] / "scripts"


@lru_cache(maxsize=1)
def get_extractor():
    """Load the SkillExtractor once and reuse it.

    Building the PhraseMatcher over 120 skills takes a moment; doing it per
    request would be wasteful, and the extractor is stateless so sharing
    one instance is safe.
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    from skill_extractor import SkillExtractor      # noqa: PLC0415
    return SkillExtractor()
