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
    "roleplay_bypass": re.compile(
        r"(?:pretend|act as if) you (?:have|had|are) (?:no|without) "
        r"(?:restrictions|rules|limitations|filters|guidelines)",
        re.IGNORECASE,
    ),
    "unfiltered_mode": re.compile(
        r"\b(?:unfiltered|uncensored|unrestricted)\s+"
        r"(?:mode|version|response|ai|assistant)\b",
        re.IGNORECASE,
    ),
    "other_jailbreak_persona": re.compile(
        r"you are now (?:STAN|AIM|DUDE|JailBreak)\b",
        re.IGNORECASE,
    ),
    # Matches a fake system or admin role marker injected at the start of a
    # line inside the user's own text. Known, accepted tradeoff: a pasted log
    # or transcript that happens to start a line with "System:" or "Admin:"
    # would also match. Same risk tolerance already accepted for the phone
    # and ip_address patterns in pii.py (2.1) - narrowing this further would
    # also exclude real injection attempts using this exact framing.
    "fake_role_marker": re.compile(
        r"^\s*\[?(?:system|admin)\]?\s*:",
        re.IGNORECASE | re.MULTILINE,
    ),
    "extract_instructions": re.compile(
        r"\b(?:print|output|repeat|show me)\s+your\s+(?:system\s+)?"
        r"(?:prompt|instructions)\b",
        re.IGNORECASE,
    ),
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
