"""Cheap-tier toxicity scanner: keyword/phrase heuristic.

Deliberately a minimal stub (per STATUS.md 2.6: "even a stub heuristic" is
the target here, not real coverage). forks.md locks cheap-tier evaluators to
regex/rule-based only, no ML dependency, so this is a small set of clearly
identifiable toxic/hateful phrasings, not a slur or profanity word list -
accepted as a permanent, high-false-negative limitation (see decisions.md,
2.6), the same tradeoff precedent pii.py's phone/ip_address patterns and
prompt_injection.py's fake_role_marker pattern already set.
"""

import re

from app.evaluators.types import DEFAULT_CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "direct_insult": re.compile(
        r"\b(?:you're|you are)\s+(?:a\s+)?(?:worthless|pathetic|an idiot|a moron|disgusting|stupid)\b",
        re.IGNORECASE,
    ),
    "death_wish_or_threat": re.compile(
        r"\b(?:kill yourself|i hope you die|i will kill you|i'll kill you)\b",
        re.IGNORECASE,
    ),
    "dehumanizing_language": re.compile(
        r"\b(?:you are|they are|those people are)\s+(?:subhuman|vermin|scum)\b",
        re.IGNORECASE,
    ),
}

# 8.1: this file was already curated down to only unambiguous phrasings
# (2.6's own docstring: "not a slur or profanity word list"), specifically
# for high precision - no further per-pattern split is warranted within an
# already-narrow, already-high-precision set. See
# .agents/prompts/8.1-policy-profile-enforcement-plan.md.
_CONFIDENCE = {
    "direct_insult": 0.95,
    "death_wish_or_threat": 0.95,
    "dehumanizing_language": 0.95,
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.toxicity,
                    confidence=_CONFIDENCE.get(pattern_name, DEFAULT_CONFIDENCE),
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
