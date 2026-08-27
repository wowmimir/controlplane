"""8.5 redaction helper: the first text-transformation helper in the codebase.

Two jobs, both pure functions (no dependency on the router or the DB):

- `redact_spans` builds the edited response body for a `disposition=redacted`
  turn: every matched span blanked to `[REDACTED:<category>]`.
- `masked_excerpt` builds the audit-trail string stored on every cheap-tier
  `Finding.evidence_ref`: the matched span blanked, plus ~40 characters of
  real surrounding context, so Session Drilldown can show *what* tripped a
  rule without ControlPlane ever persisting the raw sensitive text.

Only `pii` and `custom_policy` findings have a span that points at sensitive
data rather than at trigger phrasing, so only those are redacted from a
released response (`REDACTABLE_CATEGORIES`). A `[REDACTED:...]` token inside a
`masked_excerpt` for any other category just marks the matched span; it does
not mean the live response was edited.

See .agents/prompts/8.5-redact-and-release-plan.md.
"""

from collections.abc import Sequence

from app.models import FindingCategory

REDACTABLE_CATEGORIES = {FindingCategory.pii, FindingCategory.custom_policy}
MASKED_EXCERPT_CONTEXT = 40


def redaction_token(category: FindingCategory) -> str:
    return f"[REDACTED:{category.value}]"


def masked_excerpt(text: str, span: Sequence[int], category: FindingCategory) -> str:
    """The matched span blanked, with up to MASKED_EXCERPT_CONTEXT characters
    of real context each side and a leading/trailing ellipsis when the
    context is truncated mid-text. Never contains the raw match.
    """
    start, end = span
    left = text[max(0, start - MASKED_EXCERPT_CONTEXT):start]
    right = text[end:end + MASKED_EXCERPT_CONTEXT]
    prefix = "…" if start - MASKED_EXCERPT_CONTEXT > 0 else ""
    suffix = "…" if end + MASKED_EXCERPT_CONTEXT < len(text) else ""
    return f"{prefix}{left}{redaction_token(category)}{right}{suffix}"


def redact_spans(text: str, spans: Sequence[tuple[Sequence[int], FindingCategory]]) -> str:
    """Blank every given span to its category's redaction token.

    Spans are sorted by start; any span overlapping one already accepted is
    dropped (a single scan can produce two patterns matching overlapping
    ranges). Accepted spans are then replaced from rightmost to leftmost so
    each replacement leaves the offsets of the not-yet-replaced spans valid.
    """
    ordered = sorted(spans, key=lambda item: item[0][0])
    accepted: list[tuple[Sequence[int], FindingCategory]] = []
    last_end = -1
    for span, category in ordered:
        if span[0] >= last_end:
            accepted.append((span, category))
            last_end = span[1]
    out = text
    for (start, end), category in sorted(accepted, key=lambda item: item[0][0], reverse=True):
        out = out[:start] + redaction_token(category) + out[end:]
    return out
