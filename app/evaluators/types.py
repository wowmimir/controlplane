"""Shared types for evaluator scanners, kept separate from cheap.py's
orchestrator to avoid a circular import (pii.py/prompt_injection.py import
FindingCandidate; cheap.py imports their scan() functions).
"""

from dataclasses import dataclass

from app.models import FindingCategory

# Regex matches are deterministic (a pattern either matches or it doesn't),
# so every cheap-tier hit gets this fixed high confidence rather than a
# computed score. Also the strike-increment threshold from forks.md Fork #3
# ("increment when confidence > 0.7"), so any cheap-tier match strikes.
CONFIDENCE = 0.95


@dataclass
class FindingCandidate:
    category: FindingCategory
    confidence: float
    evidence_ref: dict | None = None
