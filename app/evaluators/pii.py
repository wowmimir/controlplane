"""Cheap-tier PII scanner: regex matches for common PII shapes.

Exact patterns are explicitly not locked by forks.md ("Exact regex patterns /
heuristic rules for cheap-tier evaluators" is fair game to decide during
build) - this is a minimal, reversible starting set. Each match is a
deterministic regex hit, so confidence is a fixed high value rather than a
computed score (see CONFIDENCE in evaluators/cheap.py).
"""

import re
from typing import Callable

from app.evaluators.types import DEFAULT_CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "email": re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"),
    # Every separator used to be optional, so this reduced to "any 10
    # consecutive digits" and flagged order ids, byte counts, etc. Now
    # requires a parenthesized area code or a separator right after it, so
    # a bare digit run no longer matches. A dot-separated or space-grouped
    # false positive (e.g. a version-like string) is an accepted, permanent
    # limitation (see decisions.md, 2.1) rather than tightened further:
    # dots/spaces are legitimate real phone formatting too.
    "phone": re.compile(
        r"(?<!\d)(?:\+?1[-.\s])?(?:\(\d{3}\)|\d{3}[-.\s])[-.\s]?\d{3}[-.\s]?\d{4}(?!\d)"
    ),
    "ssn": re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
    "ip_address": re.compile(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\b"
    ),
    # Restricted to real card-network BIN prefixes (Visa/Mastercard/Amex/
    # Discover) plus a Luhn checksum below, so this can't degrade into
    # "any grouped 13-19 digit run" the way the old phone regex once did.
    "credit_card": re.compile(
        r"(?<!\d)(?:"
        r"3[47]\d{2}[ -]?\d{6}[ -]?\d{5}"
        r"|(?:4\d{3}|5[1-5]\d{2}|6011|65\d{2})[ -]?\d{4}[ -]?\d{4}(?:[ -]?\d{1,4})?"
        r")(?!\d)"
    ),
}

# 8.1: per-pattern confidence, replacing the old flat CONFIDENCE=0.95 used by
# every pattern. credit_card is Luhn-validated (near-certain); ssn/email are
# rigid, low-collision shapes; phone already carries an accepted residual
# false-positive risk (2.1); ip_address is indistinguishable from a
# version-like string by regex alone (2.1's own accepted limitation) - below
# STRIKE_THRESHOLD, so a match still blocks this turn but no longer
# strikes/escalates. See .agents/prompts/8.1-policy-profile-enforcement-plan.md.
_CONFIDENCE = {
    "credit_card": 0.99,
    "ssn": 0.95,
    "email": 0.95,
    "phone": 0.75,
    "ip_address": 0.6,
}


def _luhn_valid(digits: str) -> bool:
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


_VALIDATORS: dict[str, Callable[[str], bool]] = {
    "credit_card": lambda raw: _luhn_valid(re.sub(r"[ -]", "", raw)),
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        validator = _VALIDATORS.get(pattern_name)
        for match in pattern.finditer(text):
            if validator is not None and not validator(match.group()):
                continue
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.pii,
                    confidence=_CONFIDENCE.get(pattern_name, DEFAULT_CONFIDENCE),
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
