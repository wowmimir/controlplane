"""Shared types for evaluator scanners, kept separate from cheap.py's
orchestrator to avoid a circular import (pii.py/prompt_injection.py import
FindingCandidate; cheap.py imports their scan() functions).
"""

from dataclasses import dataclass

from app.models import FindingCategory

# 8.1: each evaluator file now assigns confidence per pattern (a _CONFIDENCE
# map next to its _PATTERNS dict), reflecting that pattern's real precision -
# a Luhn-validated credit_card is far more certain than an ip_address regex
# that can't be told apart from a version string. This is only the fallback
# for a pattern name missing from its file's _CONFIDENCE map (should not
# normally be reached - every pattern should have an explicit entry).
DEFAULT_CONFIDENCE = 0.95


@dataclass
class FindingCandidate:
    category: FindingCategory
    confidence: float
    evidence_ref: dict | None = None
