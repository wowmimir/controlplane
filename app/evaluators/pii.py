"""Cheap-tier PII scanner: regex matches for common PII shapes.

Exact patterns are explicitly not locked by forks.md ("Exact regex patterns /
heuristic rules for cheap-tier evaluators" is fair game to decide during
build) - this is a minimal, reversible starting set. Each match is a
deterministic regex hit, so confidence is a fixed high value rather than a
computed score (see CONFIDENCE in evaluators/cheap.py).
"""

import re

from app.evaluators.types import CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    # Every separator used to be optional, so this reduced to "any 10
    # consecutive digits" and flagged order ids, byte counts, etc. Now
    # requires a parenthesized area code or a separator right after it, so
    # a bare digit run no longer matches. Remaining false positives (a
    # dot-separated version string, space-grouped digits) are 2.1's job.
    "phone": re.compile(
        r"(?<!\d)(?:\+?1[-.\s])?(?:\(\d{3}\)|\d{3}[-.\s])[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
    ),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.pii,
                    confidence=CONFIDENCE,
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
