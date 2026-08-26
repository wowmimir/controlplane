"""Cheap-tier orchestrator: runs every cheap-tier scanner against one text
blob. Reused for both request-side (1.3) and response-side (2.3) text.
"""

from app.evaluators import bias, pii, prompt_injection, secrets, toxicity
from app.evaluators.types import DEFAULT_CONFIDENCE, FindingCandidate

__all__ = ["DEFAULT_CONFIDENCE", "FindingCandidate", "run_cheap_tier"]


def run_cheap_tier(text: str) -> list[FindingCandidate]:
    return [
        *pii.scan(text),
        *prompt_injection.scan(text),
        *toxicity.scan(text),
        *bias.scan(text),
        *secrets.scan(text),
    ]
