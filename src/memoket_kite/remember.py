"""Prepare one remember() call for structured fact extraction."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Mapping, Sequence
from uuid import uuid4

from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE
from memoket_kite.errors import ConfigurationError, KiteError
from memoket_kite.pipeline.extract import extract_facts as _extract_facts

_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\uFFFE\uFFFF]")


def build_session(
    messages: Sequence[Mapping[str, str] | tuple[str, str]],
    *,
    session_id: str | None,
    session_date: str | date | datetime | None,
    title: str | None = None,
) -> dict:
    """Validate messages and build the session consumed by the extraction pipeline.

    ``utterances`` are kept as tuples for the internal XML writer; callers only
    interact with the public ``messages`` input accepted by ``Memory.remember``.
    """
    if isinstance(messages, (str, bytes)):
        raise KiteError("messages must be a non-empty sequence of messages")
    utterances = []
    for position, message in enumerate(messages, 1):
        if isinstance(message, Mapping):
            role, content = message.get("role"), message.get("content")
        elif isinstance(message, tuple) and len(message) == 2:
            role, content = message
        else:
            raise KiteError(
                "each message must be a {role, content} mapping or a (role, content) tuple"
            )
        role, content = str(role or "").strip(), str(content or "").strip()
        if not role or not content:
            raise KiteError("every message needs non-empty role and content")
        if _XML_ILLEGAL.search(role) or _XML_ILLEGAL.search(content):
            raise KiteError("message role and content cannot contain XML control characters")
        utterances.append((position, role, content))
    if not utterances:
        raise KiteError("messages cannot be empty")

    resolved_session_id = str(session_id or f"session-{uuid4().hex}").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", resolved_session_id):
        raise KiteError("session_id may contain letters, numbers, dots, underscores, and hyphens")
    if isinstance(session_date, datetime):
        resolved_date = session_date.date().isoformat()
    elif isinstance(session_date, date):
        resolved_date = session_date.isoformat()
    else:
        resolved_date = str(session_date or date.today().isoformat())
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", resolved_date):
        raise KiteError("date must be an ISO date (YYYY-MM-DD)")
    try:
        date.fromisoformat(resolved_date)
    except ValueError as exc:
        raise KiteError("date must be a valid ISO date (YYYY-MM-DD)") from exc
    if title is not None and not isinstance(title, str):
        raise ConfigurationError("title must be a string")
    title = str(title or "")
    if _XML_ILLEGAL.search(title):
        raise ConfigurationError("title cannot contain XML control characters")
    speakers = tuple(dict.fromkeys(role.lower() for _, role, _ in utterances))
    return {
        "id": resolved_session_id,
        "date": resolved_date,
        "title": title,
        "speakers": speakers,
        "utterances": [
            (f"{resolved_session_id}L{position}", role, "", content)
            for position, role, content in utterances
        ],
    }


def extract_facts(
    vocabulary,
    session: dict,
    *,
    model: str,
    include_facets: bool | None = None,
) -> list[dict]:
    """Extract structured facts from one normalized conversation session."""
    return _extract_facts(
        vocabulary,
        DEFAULT_MEMORY_PROFILE,
        session,
        model=model,
        log=lambda _: None,
        include_facets=include_facets,
    )
