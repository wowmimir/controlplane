"""Fixed choice fields, per forks.md's locked taxonomy. Each maps to a native
Postgres ENUM type (see app/db.py's Base and the model columns that use these).
"""

import enum


class PolicyProfile(str, enum.Enum):
    strict = "strict"
    balanced = "balanced"
    fast = "fast"


class FailMode(str, enum.Enum):
    fail_open = "fail_open"
    fail_closed = "fail_closed"


class EvaluatorTier(str, enum.Enum):
    cheap = "cheap"
    medium = "medium"
    expensive = "expensive"


class FindingCategory(str, enum.Enum):
    pii = "pii"
    hallucination = "hallucination"
    toxicity = "toxicity"
    bias = "bias"
    prompt_injection = "prompt_injection"
    custom_policy = "custom_policy"


class Disposition(str, enum.Enum):
    """8.2: what ControlPlane actually decided about an Execution. `clean` -
    nothing found. `flagged` - a cheap-tier hit on a fast-profile workload;
    logged for review, released as 200 anyway. `blocked` - a hard 403,
    either a cheap-tier hit on a strict/balanced workload or a session-level
    escalation block (which has no Finding to point to, see Execution's own
    docstring). See .agents/prompts/8.2-tiered-decision-logic-plan.md.
    """

    clean = "clean"
    flagged = "flagged"
    blocked = "blocked"
