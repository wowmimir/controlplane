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
