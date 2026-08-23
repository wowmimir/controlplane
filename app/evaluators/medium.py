"""Medium tier: embedding similarity grounding/hallucination check.

Stubbed per the 2026-08-23 correction (see decisions.md): real hallucination
detection deferred to Phase 2.5 (LLM-as-judge). ControlPlane has no RAG or
knowledge base to ground a response against, so a real embedding similarity
check would only be a weak, uncalibrated topical-drift proxy - not worth the
sentence-transformers/torch dependency for a heuristic Phase 2.5 will do
better by reasoning about content directly. This wires the plumbing
(signature, threshold, Finding shape) so 2.5 can drop in real logic without
another pass through app/routers/chat.py. See
.agents/prompts/2.4-medium-embedding-stub-plan.md.
"""

from app.evaluators.types import FindingCandidate

_SIMILARITY_THRESHOLD = 0.3  # unused until 2.5 wires real comparison logic


def run_medium_tier(
    context_text: str, response_text: str, budget_remaining_ms: float
) -> list[FindingCandidate]:
    # TODO: Phase 2.5 (LLM-as-judge) implements real semantic judgment.
    return []
