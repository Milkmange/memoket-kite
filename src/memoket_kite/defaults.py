"""Built-in prompts and rules used by the standard Memory workflow."""

from __future__ import annotations

import re

from memoket_kite.prompts.answer import (
    DEFAULT_ANSWER_PROMPT,
    DEFAULT_ATTRIBUTION_ANSWER,
)
from memoket_kite.prompts.extract import (
    DEFAULT_EXTRACT_PROMPT,
    DEFAULT_EXTRACT_PROMPT_NO_FACETS,
)
from memoket_kite.prompts.recall import DEFAULT_COMPILE_PROMPT


class DefaultMemoryProfile:
    """The built-in English extraction and retrieval profile for Memory."""

    SESSION_TAG = "session"
    KINDS = ("event", "plan", "preference", "identity", "relationship", "opinion", "other")
    EVENTS = (
        "meeting",
        "decision",
        "deadline",
        "milestone",
        "trip",
        "move",
        "purchase",
        "sale",
        "job_change",
        "health_event",
        "relationship_event",
        "celebration",
        "competition",
        "release",
        "incident",
    )
    EXTRACT_FACETS = True
    ATTRIBUTION_ANSWER = DEFAULT_ATTRIBUTION_ANSWER
    EXTRACT_PROMPT = DEFAULT_EXTRACT_PROMPT
    EXTRACT_PROMPT_NO_FACETS = DEFAULT_EXTRACT_PROMPT_NO_FACETS
    COMPILE_PROMPT = DEFAULT_COMPILE_PROMPT
    ANSWER_PROMPT = DEFAULT_ANSWER_PROMPT

    @staticmethod
    def keywords(question: str) -> list[str]:
        return sorted(set(re.findall(r"[a-zA-Z][a-zA-Z']{2,}", question.lower())))


DEFAULT_MEMORY_PROFILE = DefaultMemoryProfile
