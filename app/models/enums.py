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


class ReviewStatus(str, enum.Enum):
    """8.3: an operator's judgment on a Finding. `unreviewed` - nobody has
    looked at it yet (the default for every finding, historical rows
    included). `confirmed` - a real detection. `false_positive` - the pattern
    fired on benign content. Feeds the Dashboard trust metric (false-positive
    rate of reviewed findings) and Detection Health's per-pattern FP rate. See
    .agents/prompts/8.3-finding-feedback-loop-plan.md.
    """

    unreviewed = "unreviewed"
    confirmed = "confirmed"
    false_positive = "false_positive"


class Disposition(str, enum.Enum):
    """8.2: what ControlPlane actually decided about an Execution. `clean` -
    nothing found. `flagged` - a cheap-tier hit on a fast-profile workload;
    logged for review, released as 200 anyway. `blocked` - a hard 403,
    either a cheap-tier hit on a strict/balanced workload or a session-level
    escalation block (which has no Finding to point to, see Execution's own
    docstring). `redacted` (8.5) - a balanced-profile workload's response-side
    hit where every cheap-tier candidate is `pii`/`custom_policy`: the matched
    span(s) are blanked to `[REDACTED:<category>]` and the edited response is
    released as 200, the rubric's fourth "edit" decision tier. See
    .agents/prompts/8.2-tiered-decision-logic-plan.md and
    .agents/prompts/8.5-redact-and-release-plan.md.
    """

    clean = "clean"
    flagged = "flagged"
    blocked = "blocked"
    redacted = "redacted"
