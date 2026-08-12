"""Profile contract used by the natural-language Reasoner."""

from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from memoket_kite.research.errors import ReasonerConfigurationError


@runtime_checkable
class ReasonerProfile(Protocol):
    """Minimum profile surface for natural-language retrieval and answering."""

    KINDS: Sequence[str]
    COMPILE_PROMPT: str
    ANSWER_PROMPT: str
    ATTRIBUTION_ANSWER: str

    def keywords(self, question: str) -> list[str]: ...


def validate_profile(profile: object) -> None:
    """Fail early without promoting optional research switches to public API."""
    missing = [
        name
        for name in ("KINDS", "COMPILE_PROMPT", "ANSWER_PROMPT", "ATTRIBUTION_ANSWER")
        if not hasattr(profile, name)
    ]
    if not callable(getattr(profile, "keywords", None)):
        missing.append("keywords")
    if missing:
        joined = ", ".join(missing)
        raise ReasonerConfigurationError(f"reasoner profile is missing required members: {joined}")
