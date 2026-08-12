"""The small, application-facing API for KITE symbolic memory."""

from __future__ import annotations

import copy
import typing
from datetime import date, datetime
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE
from memoket_kite.errors import (
    ConfigurationError,
    KiteError,
    ProviderError,
    QueryError,
    StorageError,
)
from memoket_kite.fact import Answer, Fact, fact_from_stored
from memoket_kite.providers.llm import ensure_configured
from memoket_kite.remember import build_session, extract_facts
from memoket_kite.research.codebook import Codebook, Reasoner
from memoket_kite.storage import PathInput, append_session, source_paths


def _reference_date(value: str | date | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        raise ConfigurationError("reference_date must be an ISO date (YYYY-MM-DD)")
    resolved = value.strip()
    if not resolved:
        return ""
    try:
        parsed = date.fromisoformat(resolved)
    except ValueError as exc:
        raise ConfigurationError("reference_date must be a valid ISO date (YYYY-MM-DD)") from exc
    if parsed.isoformat() != resolved:
        raise ConfigurationError("reference_date must be an ISO date (YYYY-MM-DD)")
    return resolved


def _raise_public_error(exc: Exception, message: str) -> "typing.NoReturn":
    """Translate an internal failure into the public error contract.

    The research API wraps everything in its own ResearchError hierarchy, so
    a provider outage surfaces there as ReasoningError with the ProviderError
    as its cause. The Memory boundary walks the cause chain and re-raises the
    ProviderError itself: `except ProviderError` is what the public API
    documents, and a re-labelled provider failure is uncatchable by contract.
    """
    cause: BaseException | None = exc
    while cause is not None:
        if isinstance(cause, ProviderError):
            raise cause
        cause = cause.__cause__
    raise KiteError(f"{message}: {exc}") from exc


class Memory:
    """A durable symbolic memory loaded from one or more XML artifacts."""

    def __init__(
        self,
        paths: tuple[Path, ...],
        book: Codebook,
        *,
        model: str,
        answer_model: str,
        reference_date: str,
    ):
        self._paths = paths
        self._book = book
        self._model = model
        self._answer_model = answer_model
        self._reference_date = reference_date

    @classmethod
    def load(
        cls,
        source: PathInput | Iterable[PathInput],
        *,
        model: str | None = None,
        answer_model: str | None = None,
        reference_date: str | date | datetime | None = None,
    ) -> "Memory":
        """Load XML memory from one or more artifacts."""
        selected_model = str(model or "gpt-4.1-mini").strip()
        try:
            paths = source_paths(source)
            book = Codebook.load(paths)
        except KiteError:
            raise
        except Exception as exc:
            raise StorageError(f"could not load memory: {exc}") from exc
        return cls(
            paths,
            book,
            model=selected_model,
            answer_model=str(answer_model or selected_model),
            reference_date=_reference_date(reference_date),
        )

    def remember(
        self,
        messages: Sequence[Mapping[str, str] | tuple[str, str]],
        *,
        session_id: str | None = None,
        date: str | date | datetime | None = None,
        title: str | None = None,
        include_facets: bool = True,
    ) -> list[Fact]:
        """Experimental: extract and persist facts from one conversation session.

        One LLM call extracts both Facts and retrieval facets;
        ``include_facets=False`` requests Facts alone, leaving the object,
        place, event, and duration facets unset. Persisting rewrites the whole
        artifact and takes no lock, so two writers against the same file are
        not supported. Everything that reaches disk arrives through a named
        parameter of this method.
        """
        if len(self._paths) != 1:
            raise KiteError("remember requires Memory.load() with exactly one XML file")
        if not isinstance(include_facets, bool):
            raise KiteError("include_facets must be a bool")
        try:
            session = build_session(
                messages,
                session_id=session_id,
                session_date=date,
                title=title,
            )
            # Refuse a duplicate before the extraction call, not after: the
            # storage layer's own check still holds, but discovering the
            # conflict there means a full LLM call was already paid for.
            if session["id"] in self._book._store.units:
                raise StorageError(f"session_id already exists: {session['id']}")
            self._require_provider(self._model)
            # Extraction proposes topics into the vocabulary as it reads. Give
            # it a copy, not the live one: if the write below fails, a live
            # vocabulary keeps the phantom proposals in memory and the next
            # successful remember() silently persists them.
            staged_vocab = copy.deepcopy(self._book._vocab)
            facts = extract_facts(
                staged_vocab,
                session,
                model=self._model,
                include_facets=include_facets,
            )
            append_session(self._paths[0], session, facts, staged_vocab)
        except KiteError:
            raise
        except Exception as exc:
            _raise_public_error(exc, "could not remember this session")
        try:
            self._book = Codebook.load(self._paths[0])
            return [
                fact_from_stored(self._book.inspect().fact(f"{session['id']}F{i}"))
                for i in range(1, len(facts) + 1)
            ]
        except Exception as exc:
            # The session IS on disk at this point, so the message has to say
            # so: a caller who reads this as a failed write retries the same
            # session and is refused by the duplicate-id check.
            raise StorageError(
                f"session {session['id']!r} was persisted, but reloading the memory "
                f"failed ({exc}); call Memory.load() again"
            ) from exc

    def recall(
        self,
        query: str,
        *,
        limit: int = 10,
    ) -> list[Fact]:
        """Recall structured facts relevant to a natural-language query.

        Only facts are returned. Retrieval may also surface raw conversation
        lines and session records as supporting evidence; those are not facts,
        and dressing one up as a ``Fact`` with every field blank would hand
        the caller a type that lies. The utterances behind each fact remain
        visible as its ``sources``.
        """
        self._validate_question(query, limit)
        try:
            self._require_provider(self._model)
            result = self._reasoner().retrieve(str(query), evidence_limit=limit)
        except KiteError:
            raise
        except Exception as exc:
            _raise_public_error(exc, "could not recall memories")
        return [fact_from_stored(item) for item in result.evidence if item.type == "fact"]

    def answer(
        self,
        question: str,
        *,
        limit: int = 10,
    ) -> str:
        """Answer a question from recalled evidence."""
        return self.answer_with_evidence(question, limit=limit).text

    def answer_with_evidence(
        self,
        question: str,
        *,
        limit: int = 10,
    ) -> Answer:
        """Answer a question and keep the receipts.

        Returns the answer text together with the facts the reader was shown
        and the provenance IDs it cited. A citation may name a Fact, a raw
        source line, or a deduplicated instance rendered in the evidence pack.
        Raw lines and instances are evidence context rather than Facts, so
        their IDs can appear in ``citations`` without appearing in
        ``evidence``.
        """
        self._validate_question(question, limit)
        try:
            self._require_provider(self._model)
            self._require_provider(self._answer_model)
            result = self._reasoner().answer(str(question), evidence_limit=limit)
        except KiteError:
            raise
        except Exception as exc:
            _raise_public_error(exc, "could not answer question")
        return Answer(
            question=result.question,
            text=result.answer,
            evidence=tuple(
                fact_from_stored(item) for item in result.evidence if item.type == "fact"
            ),
            citations=result.citation_ids,
        )

    @staticmethod
    def _validate_question(question: str, limit: int) -> None:
        if not str(question or "").strip():
            raise QueryError("question cannot be empty")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise QueryError("limit must be a positive integer")

    def _reasoner(self) -> Reasoner:
        return Reasoner(
            self._book,
            profile=DEFAULT_MEMORY_PROFILE,
            model=self._model,
            answer_model=self._answer_model,
            reference_date=self._reference_date or None,
        )

    @staticmethod
    def _require_provider(model: str) -> None:
        try:
            ensure_configured(model)
        except RuntimeError as exc:
            raise ProviderError(str(exc)) from exc
