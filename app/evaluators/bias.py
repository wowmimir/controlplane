"""Cheap-tier bias scanner: keyword/phrase heuristic.

Deliberately a minimal stub, same rationale as toxicity.py (see
decisions.md, 2.6): a regex keyword list is a weak proxy for bias, real
coverage is out of reach at the cheap tier per forks.md's "no ML dependency"
lock and is left to a future medium-tier (embedding) or classifier
approach if ever needed.
"""

import re

from app.evaluators.types import DEFAULT_CONFIDENCE, FindingCandidate
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

# 8.1: this file's own module docstring calls these patterns "a weak proxy
# for bias" - a generalization-shaped sentence can be neutral or even
# corrective in intent, which a regex cannot distinguish. Below
# STRIKE_THRESHOLD: a match still blocks this turn (cheap tier's existing
# "any match blocks unconditionally" rule, unaffected) but no longer
# strikes/escalates. See .agents/prompts/8.1-policy-profile-enforcement-plan.md.
_CONFIDENCE = {
    "absolute_group_generalization": 0.65,
    "inherent_trait_claim": 0.65,
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.bias,
                    confidence=_CONFIDENCE.get(pattern_name, DEFAULT_CONFIDENCE),
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
