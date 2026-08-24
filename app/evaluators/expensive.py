"""Expensive tier: LLM-as-judge hallucination detection.

Runs only via BackgroundTasks, after the response has already been
released to the caller (see app/routers/chat.py's
_run_expensive_tier_task) - per forks.md Fork #4, it can update the
session ledger and the audit trail but can never block or alter the
response that triggered it. Reuses the same configured model as 1.4's
primary model call (no dedicated judge model/env var - ratified during
.agents/prompts/2.5-expensive-llm-as-judge-plan.md).
"""

import json
import logging

from app.evaluators.types import FindingCandidate
from app.model_client import ModelCallError, call_model
from app.models import FindingCategory
from app.schemas.chat import ChatCompletionRequest, ChatMessage

logger = logging.getLogger(__name__)

# Same default model 1.4/model_client.py already targets - no separate
# judge model. call_model() ignores this field's exact value beyond
# forwarding it to the model API, so reusing whatever model the caller's
# own request used is not required; a fixed constant keeps this evaluator
# independent of the triggering request's model choice.
_JUDGE_MODEL = "minimax-m3:cloud"

_JUDGE_SYSTEM_PROMPT = (
    "You are a strict fact-checking judge. Given a CONTEXT (a user's "
    "conversation) and a RESPONSE (an AI model's reply to it), decide "
    "whether the RESPONSE asserts any claim that is not supported by, or "
    "is contradicted by, the CONTEXT. Reply with ONLY a JSON object, no "
    "other text, no markdown code fences, in exactly this shape: "
    '{"hallucination": <true|false>, "confidence": <0.0-1.0>, '
    '"reasoning": "<one sentence>"}.'
)


async def run_expensive_tier(context_text: str, response_text: str) -> list[FindingCandidate]:
    """Ask the judge model whether response_text hallucinates relative to
    context_text. Any doubt - a failed model call, unparseable output, or
    an explicit "no" verdict - resolves to []. Never raises.
    """
    judge_request = ChatCompletionRequest(
        model=_JUDGE_MODEL,
        messages=[
            ChatMessage(role="system", content=_JUDGE_SYSTEM_PROMPT),
            ChatMessage(
                role="user",
                content=f"CONTEXT:\n{context_text}\n\nRESPONSE:\n{response_text}",
            ),
        ],
    )

    try:
        judge_response, _latency_ms = await call_model(judge_request)
    except ModelCallError as exc:
        logger.error("expensive-tier judge call failed (code=%s): %s", exc.code, exc.message)
        return []

    raw = judge_response.choices[0].message.content
    try:
        verdict = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        logger.error("expensive-tier judge returned unparseable output: %r", raw)
        return []

    if not isinstance(verdict, dict) or not verdict.get("hallucination"):
        return []

    try:
        confidence = max(0.0, min(1.0, float(verdict.get("confidence", 0.0))))
    except (TypeError, ValueError):
        confidence = 0.0

    return [
        FindingCandidate(
            category=FindingCategory.hallucination,
            confidence=confidence,
            evidence_ref={
                "reasoning": verdict.get("reasoning"),
                "judge_model": _JUDGE_MODEL,
            },
        )
    ]
