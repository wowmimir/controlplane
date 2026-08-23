"""Cheap-tier prompt injection scanner: keyword/phrase heuristic.

Exact patterns are explicitly not locked by forks.md - this is a minimal,
reversible starting set of common jailbreak/override phrases.
"""

import re

from app.evaluators.types import CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "ignore_instructions": re.compile(r"ignore (?:all )?(?:previous|prior|above) instructions", re.IGNORECASE),
    "disregard_above": re.compile(r"disregard (?:the )?(?:above|previous|prior)", re.IGNORECASE),
    "reveal_system_prompt": re.compile(r"reveal (?:your )?(?:system )?prompt", re.IGNORECASE),
    "dan_jailbreak": re.compile(r"you are now (?:DAN|in developer mode)", re.IGNORECASE),
    "new_instructions": re.compile(r"new instructions:?\s", re.IGNORECASE),
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.prompt_injection,
                    confidence=CONFIDENCE,
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
