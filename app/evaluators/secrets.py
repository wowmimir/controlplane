"""Cheap-tier secret/API-key scanner, feeds FindingCategory.custom_policy
(not pii - a leaked credential is not personal data about a person).

Patterns AKIA/sk-/ghp_ were drafted during 2.1 and deferred here (see
decisions.md, 2.1); pem_private_key and slack_token were added during 2.6 to
round out common real-world secret shapes. None of these formats carry a
checksum, so unlike pii.py's credit_card, no _VALIDATORS entry is needed.
"""

import re

from app.evaluators.types import CONFIDENCE, FindingCandidate
from app.models import FindingCategory

_PATTERNS = {
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "generic_secret_token": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bghp_[A-Za-z0-9]{36}\b"),
    "pem_private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "slack_token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b"),
}


def scan(text: str) -> list[FindingCandidate]:
    candidates = []
    for pattern_name, pattern in _PATTERNS.items():
        for match in pattern.finditer(text):
            candidates.append(
                FindingCandidate(
                    category=FindingCategory.custom_policy,
                    confidence=CONFIDENCE,
                    evidence_ref={
                        "pattern": pattern_name,
                        "span": [match.start(), match.end()],
                    },
                )
            )
    return candidates
