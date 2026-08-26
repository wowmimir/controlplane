"""Cheap-tier secret/API-key scanner, feeds FindingCategory.custom_policy
(not pii - a leaked credential is not personal data about a person).

Patterns AKIA/sk-/ghp_ were drafted during 2.1 and deferred here (see
decisions.md, 2.1); pem_private_key and slack_token were added during 2.6 to
round out common real-world secret shapes. None of these formats carry a
checksum, so unlike pii.py's credit_card, no _VALIDATORS entry is needed.
"""

import re

from app.evaluators.types import DEFAULT_CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic_secret_token": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "pem_private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
}

# 8.1: per-pattern confidence. aws_access_key/github_token/pem_private_key
# are highly distinctive fixed-prefix/fixed-header shapes, effectively
# unique to their real format. slack_token's prefix family is distinctive
# but has a slightly broader character class. generic_secret_token ("sk-...")
# is the most generic prefix of the five - a plausible (if unlikely)
# collision with a non-secret token-shaped string, the same class of
# residual risk pii.py's phone pattern already accepts. See
# .agents/prompts/8.1-policy-profile-enforcement-plan.md.
_CONFIDENCE = {
    "aws_access_key": 0.95,
    "github_token": 0.95,
    "pem_private_key": 0.95,
    "slack_token": 0.9,
    "generic_secret_token": 0.85,
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.custom_policy,
                    confidence=_CONFIDENCE.get(pattern_name, DEFAULT_CONFIDENCE),
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
