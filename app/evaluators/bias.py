"""Cheap-tier bias scanner: keyword/phrase heuristic.

Deliberately a minimal stub, same rationale as toxicity.py (see
decisions.md, 2.6): a regex keyword list is a weak proxy for bias, real
coverage is out of reach at the cheap tier per forks.md's "no ML dependency"
lock and is left to a future medium-tier (embedding) or classifier
approach if ever needed.
"""

import re

from app.evaluators.types import CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "absolute_group_generalization": re.compile(
        r"\ball\s+(?:women|men|muslims|christians|jews|asians|black people|white people|"
        r"latinos|immigrants|gay people|trans people)\s+(?:are|do|want|believe)\b",
        re.IGNORECASE,
    ),
    "inherent_trait_claim": re.compile(
        r"\b(?:women|men)\s+are\s+(?:naturally|inherently|always|never)\b",
        re.IGNORECASE,
    ),
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.bias,
                    confidence=CONFIDENCE,
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
