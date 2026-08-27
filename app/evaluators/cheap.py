"""Cheap-tier orchestrator: runs every cheap-tier scanner against one text
blob. Reused for both request-side (1.3) and response-side (2.3) text.

8.6: an optional per-workload `category_overrides` map (read from
`Workload.metadata` by the two `run_cheap_tier` call sites in
`app/routers/chat.py`) can, per category, disable the scanner, raise a
confidence bar, or suppress named patterns. All three just shorten the
returned candidate list; nothing downstream (Finding rows, ledger strikes,
disposition, redaction) changes shape. See
.agents/prompts/8.6-per-workload-category-overrides-plan.md.
"""

from app.evaluators import bias, pii, prompt_injection, secrets, toxicity
from app.evaluators.types import DEFAULT_CONFIDENCE, FindingCandidate
from app.models import FindingCategory

__all__ = ["DEFAULT_CONFIDENCE", "FindingCandidate", "run_cheap_tier"]

# Category -> its cheap-tier scanner. Order is the pre-8.6 fan-out order
# (pii, prompt_injection, toxicity, bias, secrets) so a no-override call
# returns candidates in exactly the same order as before. `hallucination`
# has no cheap scanner (expensive tier only) and is deliberately absent - an
# override key for it is ignored (see the 8.6 spec's AC-8).
_SCANNERS = {
    FindingCategory.pii: pii.scan,
    FindingCategory.prompt_injection: prompt_injection.scan,
    FindingCategory.toxicity: toxicity.scan,
    FindingCategory.bias: bias.scan,
    FindingCategory.custom_policy: secrets.scan,
}


def _rule(overrides: dict, category: FindingCategory) -> dict:
    rule = overrides.get(category.value)
    return rule if isinstance(rule, dict) else {}


def _floor(rule: dict) -> float:
    value = rule.get("confidence_floor")
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0


def run_cheap_tier(
    text: str, category_overrides: dict | None = None
) -> list[FindingCandidate]:
    """Run every cheap-tier scanner against `text`.

    `category_overrides` (8.6) is the workload's per-category tuning map,
    keyed by `FindingCategory` value:
      - `{"enabled": false}` skips that category's scanner entirely;
      - `{"confidence_floor": 0.8}` drops that category's matches below the bar;
      - `{"disabled_patterns": ["ip_address"]}` drops named patterns (the
        surface 8.3's Detection Health suppress toggle writes to).
    A `None`/absent map, or an absent category key, is exactly pre-8.6
    behavior. Malformed values degrade to "no override", never raise.
    """
    overrides = category_overrides if isinstance(category_overrides, dict) else {}
    candidates: list[FindingCandidate] = []
    for category, scan in _SCANNERS.items():
        rule = _rule(overrides, category)
        if rule.get("enabled") is False:
            continue
        floor = _floor(rule)
        raw = rule.get("disabled_patterns")
        disabled = set(raw) if isinstance(raw, (list, tuple, set)) else set()
        for candidate in scan(text):
            if candidate.confidence < floor:
                continue
            if (candidate.evidence_ref or {}).get("pattern") in disabled:
                continue
            candidates.append(candidate)
    return candidates
