"""Artifact-first API for KITE symbolic episodic memory."""

from __future__ import annotations

import os
import xml.etree.ElementTree as ET
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Iterable

from memoket_kite.core.algebra import Store, execute_plan
from memoket_kite.research.errors import (
    CodebookLoadError,
    InvalidQueryError,
    ReasonerConfigurationError,
    ReasoningError,
)
from memoket_kite.research.profile import ReasonerProfile, validate_profile
from memoket_kite.research.query import (
    Aggregate,
    AnswerResult,
    CodebookStats,
    EntityInfo,
    Evidence,
    ExecutionTrace,
    QueryPlan,
    QueryResult,
    RetrievalResult,
    SourceLine,
    SymbolicQuery,
    TopicInfo,
    TraceEvent,
)

PathInput = str | os.PathLike[str]


def _validated_reference_date(value: str | None, error_type) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise error_type("reference_date must be an ISO date (YYYY-MM-DD)")
    resolved = value.strip()
    if not resolved:
        return ""
    try:
        parsed = date.fromisoformat(resolved)
    except ValueError as exc:
        raise error_type("reference_date must be a valid ISO date (YYYY-MM-DD)") from exc
    if parsed.isoformat() != resolved:
        raise error_type("reference_date must be an ISO date (YYYY-MM-DD)")
    return resolved


def _normalize_paths(paths: PathInput | Iterable[PathInput]) -> tuple[Path, ...]:
    if isinstance(paths, (str, os.PathLike)):
        values = (paths,)
    else:
        try:
            values = tuple(paths)
        except TypeError as exc:
            raise CodebookLoadError("paths must be a path or an iterable of paths") from exc
    if not values:
        raise CodebookLoadError("at least one codebook path is required")
    normalized = tuple(Path(value).expanduser() for value in values)
    for path in normalized:
        if not path.exists():
            raise CodebookLoadError(f"codebook does not exist: {path}")
        if not path.is_file():
            raise CodebookLoadError(f"codebook path is not a file: {path}")
    return normalized


def _source_line(store: Store, source_id: str) -> SourceLine | None:
    line = store.lines.get(source_id)
    if line is None:
        return None
    return SourceLine(
        id=line.id,
        unit_id=line.unit,
        source_time=line.unit_date,
        subject=line.who,
        text=line.text,
    )


def _hydrate_row(store: Store, row: dict, *, cited_ids: set[str] | None = None) -> Evidence | None:
    cited_ids = cited_ids or set()
    row_type = str(row.get("type") or "")
    identifier = str(row.get("id") or "")
    score = row.get("score")
    score = float(score) if isinstance(score, (int, float)) else None

    if row_type == "fact" and identifier in store.facts:
        fact = store.facts[identifier]
        unit = store.units.get(fact.unit)
        sources = tuple(
            source
            for source_id in fact.src
            if (source := _source_line(store, source_id)) is not None
        )
        source_ids = tuple(fact.src)
        return Evidence(
            id=fact.id,
            type="fact",
            text=fact.text,
            unit_id=fact.unit,
            event_time=fact.t or None,
            source_time=unit.date if unit is not None else fact.unit_date or None,
            kind=fact.kind or None,
            subject=fact.who or None,
            confidence=fact.conf or None,
            topics=tuple(fact.topics),
            entities=tuple(fact.entities),
            source_ids=source_ids,
            sources=sources,
            score=score,
            cited=fact.id in cited_ids or bool(cited_ids.intersection(source_ids)),
            attributes={
                "objects": tuple(fact.obj),
                "places": tuple(fact.place),
                "events": tuple(fact.event),
                "duration": fact.dur,
            },
        )

    if row_type == "line" and identifier in store.lines:
        line = store.lines[identifier]
        source = _source_line(store, line.id)
        return Evidence(
            id=line.id,
            type="line",
            text=line.text,
            unit_id=line.unit,
            source_time=line.unit_date or None,
            subject=line.who or None,
            source_ids=(line.id,),
            sources=(source,) if source is not None else (),
            score=score,
            cited=line.id in cited_ids,
        )

    if row_type == "unit" and identifier in store.units:
        unit = store.units[identifier]
        return Evidence(
            id=unit.id,
            type="unit",
            text=unit.title or unit.id,
            unit_id=unit.id,
            source_time=unit.date or None,
            score=score,
            cited=unit.id in cited_ids,
            attributes={
                "timestamp": unit.t,
                "title": unit.title,
                "duration_minutes": unit.dur_min,
                "line_count": unit.n_lines,
            },
        )

    if row_type == "instance" and identifier in store.instances:
        instance = store.instances[identifier]
        mentions = tuple(instance.get("mentions") or ())
        return Evidence(
            id=identifier,
            type="instance",
            text=str(instance.get("label") or identifier),
            event_time=str(instance.get("t") or "") or None,
            kind=str(instance.get("kind") or "") or None,
            source_ids=mentions,
            cited=identifier in cited_ids or bool(cited_ids.intersection(mentions)),
            attributes={"mentions": mentions},
        )

    return None


def _split_rows(
    store: Store,
    rows: Iterable[dict],
    *,
    cited_ids: set[str] | None = None,
) -> tuple[tuple[Evidence, ...], tuple[Aggregate, ...]]:
    evidence: list[Evidence] = []
    aggregates: list[Aggregate] = []
    for row in rows:
        if row.get("type") == "count":
            aggregates.append(
                Aggregate(
                    operation="count",
                    value=int(row.get("n") or 0),
                    target=str(row.get("of") or ""),
                    text=str(row.get("text") or ""),
                )
            )
            continue
        item = _hydrate_row(store, row, cited_ids=cited_ids)
        if item is not None:
            evidence.append(item)
    return tuple(evidence), tuple(aggregates)


def _trace(stages: Iterable[dict]) -> ExecutionTrace:
    events = []
    for raw in stages:
        event = dict(raw)
        stage = str(event.pop("stage", ""))
        events.append(TraceEvent(stage=stage, details=event))
    return ExecutionTrace(tuple(events))


class Codebook:
    """Loaded, read-only symbolic memory representation of structured Facts."""

    def __init__(self, store: Store, vocab, paths: tuple[Path, ...]):
        self._store = store
        self._vocab = vocab
        self._paths = paths

    @classmethod
    def load(
        cls,
        paths: PathInput | Iterable[PathInput],
        *,
        strict: bool = False,
    ) -> "Codebook":
        """Load one or more Codebook shards.

        The default tolerates soft taxonomy inconsistencies, such as a posting
        for a label that ``<vocab>`` does not declare, while still enforcing
        structural and provenance validation.  ``strict=True`` also audits the
        merged taxonomy, which is the check a freshly built Codebook is
        expected to pass.
        """
        normalized = _normalize_paths(paths)
        try:
            for path in normalized:
                root = ET.parse(path).getroot()
                if root.find("timeline") is None:
                    raise CodebookLoadError(f"codebook has no timeline: {path}")
            store, vocab = Store.load([str(path) for path in normalized], strict=strict)
        except CodebookLoadError:
            raise
        except (OSError, ET.ParseError, AttributeError, TypeError, ValueError) as exc:
            raise CodebookLoadError(f"failed to load codebook: {exc}") from exc
        return cls(store, vocab, normalized)

    def query(
        self,
        query: SymbolicQuery,
        *,
        budget: int = 12,
        unit_cap: int = 4,
    ) -> QueryResult:
        if not isinstance(query, SymbolicQuery):
            raise InvalidQueryError("query must be a SymbolicQuery")
        return self.execute(query.to_plan(), budget=budget, unit_cap=unit_cap)

    def execute(
        self,
        plan: QueryPlan,
        *,
        budget: int = 12,
        unit_cap: int = 4,
    ) -> QueryResult:
        if not isinstance(plan, QueryPlan):
            raise InvalidQueryError("plan must be a QueryPlan")
        for name, value in (("budget", budget), ("unit_cap", unit_cap)):
            if not isinstance(value, int) or isinstance(value, bool) or value < 1:
                raise InvalidQueryError(f"{name} must be a positive integer")
        try:
            rows, trace = execute_plan(
                self._store,
                self._vocab,
                plan.to_dict(),
                speakers=self._store.speakers,
                budget=budget,
                unit_cap=unit_cap,
            )
        except (AttributeError, IndexError, KeyError, TypeError, ValueError) as exc:
            raise InvalidQueryError(f"query execution failed: {exc}") from exc
        evidence, aggregates = _split_rows(self._store, rows)
        return QueryResult(
            plan=plan,
            evidence=evidence,
            aggregates=aggregates,
            trace=_trace(trace.stages),
        )

    def inspect(self) -> "CodebookInspector":
        return CodebookInspector(self)


class CodebookInspector:
    """Read-only structural inspection of a loaded codebook."""

    def __init__(self, codebook: Codebook):
        self._codebook = codebook

    def summary(self) -> CodebookStats:
        store, vocab = self._codebook._store, self._codebook._vocab
        dates = sorted(unit.date for unit in store.units.values() if unit.date)
        return CodebookStats(
            shards=len(self._codebook._paths),
            units=len(store.units),
            facts=len(store.facts),
            lines=len(store.lines),
            topics=len(vocab.topics),
            entities=len(vocab.entities),
            speakers=tuple(sorted(store.speakers)),
            start_date=dates[0] if dates else None,
            end_date=dates[-1] if dates else None,
        )

    def topic_tree(self) -> str:
        return self._codebook._vocab.render_tree()

    def topics(self) -> tuple[TopicInfo, ...]:
        return tuple(
            TopicInfo(
                code=topic.code,
                parents=tuple(sorted(topic.parents)),
                status=topic.status,
                aliases=tuple(sorted(topic.aliases)),
            )
            for topic in sorted(
                self._codebook._vocab.topics.values(),
                key=lambda item: item.code,
            )
        )

    def entities(self) -> tuple[EntityInfo, ...]:
        return tuple(
            EntityInfo(
                code=entity.code,
                name=entity.name,
                type=entity.etype,
                aliases=tuple(sorted(entity.aliases)),
                relations=tuple(sorted(entity.rels)),
            )
            for entity in sorted(
                self._codebook._vocab.entities.values(),
                key=lambda item: item.code,
            )
        )

    def fact(self, fact_id: str) -> Evidence:
        item = _hydrate_row(
            self._codebook._store,
            {"type": "fact", "id": str(fact_id)},
        )
        if item is None:
            raise KeyError(f"unknown fact: {fact_id}")
        return item

    def sources(self, fact_id: str) -> tuple[SourceLine, ...]:
        return self.fact(fact_id).sources


class Reasoner:
    """Natural-language retrieval and evidence-backed answering over a Codebook."""

    def __init__(
        self,
        codebook: Codebook,
        *,
        profile: ReasonerProfile,
        model: str,
        answer_model: str | None = None,
        reference_date: str | None = None,
    ):
        if not isinstance(codebook, Codebook):
            raise ReasonerConfigurationError("codebook must be a Codebook")
        validate_profile(profile)
        if not str(model).strip():
            raise ReasonerConfigurationError("model is required")
        self._codebook = codebook
        self._profile = profile
        self._model = str(model)
        self._answer_model = str(answer_model or model)
        self._reference_date = _validated_reference_date(reference_date, ReasonerConfigurationError)

    def retrieve(
        self,
        question: str,
        *,
        evidence_limit: int = 0,
        reference_date: str | None = None,
    ) -> RetrievalResult:
        if isinstance(evidence_limit, bool) or not isinstance(evidence_limit, int):
            # The `< 0` test below cannot carry this alone: `1.5 < 0` and
            # `True < 0` both evaluate, letting a float or a bool through into
            # the row budget, and a str raises a bare TypeError out of the
            # comparison rather than this error.
            raise InvalidQueryError("evidence_limit must be an integer")
        if evidence_limit < 0:
            raise InvalidQueryError("evidence_limit cannot be negative")
        if not str(question).strip():
            raise InvalidQueryError("question cannot be empty")
        requested_date = _validated_reference_date(reference_date, InvalidQueryError)
        try:
            # Keep model-provider initialization out of ``import memoket_kite``.
            from memoket_kite.pipeline.retrieve import retrieve

            raw = retrieve(
                self._codebook._store,
                self._codebook._vocab,
                self._profile,
                str(question),
                model=self._model,
                reference_date=requested_date or self._reference_date,
                budget=evidence_limit,
            )
            plan = QueryPlan.from_dict(raw["plan"])
            evidence, aggregates = _split_rows(
                self._codebook._store,
                raw.get("rows") or (),
            )
            return RetrievalResult(
                question=str(raw.get("question") or question),
                plan=plan,
                evidence=evidence,
                aggregates=aggregates,
                trace=_trace(raw.get("trace") or ()),
                used_fallback=bool(raw.get("used_fallback")),
            )
        except (InvalidQueryError, ReasonerConfigurationError):
            raise
        except Exception as exc:
            raise ReasoningError(f"retrieval failed: {exc}") from exc

    def answer(
        self,
        question: str,
        *,
        evidence_limit: int = 0,
        reference_date: str | None = None,
    ) -> AnswerResult:
        if isinstance(evidence_limit, bool) or not isinstance(evidence_limit, int):
            # The `< 0` test below cannot carry this alone: `1.5 < 0` and
            # `True < 0` both evaluate, letting a float or a bool through into
            # the row budget, and a str raises a bare TypeError out of the
            # comparison rather than this error.
            raise InvalidQueryError("evidence_limit must be an integer")
        if evidence_limit < 0:
            raise InvalidQueryError("evidence_limit cannot be negative")
        if not str(question).strip():
            raise InvalidQueryError("question cannot be empty")
        requested_date = _validated_reference_date(reference_date, InvalidQueryError)
        try:
            # Keep model-provider initialization out of ``import memoket_kite``.
            from memoket_kite.pipeline.answer import answer

            raw = answer(
                self._codebook._store,
                self._codebook._vocab,
                self._profile,
                str(question),
                model=self._model,
                answer_model=self._answer_model,
                reference_date=requested_date or self._reference_date,
                budget=evidence_limit,
            )
            plan = QueryPlan.from_dict(raw["plan"])
            citation_ids = tuple(str(value) for value in (raw.get("cited") or ()))
            cited = set(citation_ids)
            evidence, _ = _split_rows(
                self._codebook._store,
                raw.get("pack_rows") or (),
                cited_ids=cited,
            )
            # Some internal return paths do not retain all source IDs in
            # pack_rows. Recompute the marker without changing evidence order.
            evidence = tuple(
                replace(
                    item,
                    cited=item.cited
                    or item.id in cited
                    or bool(cited.intersection(item.source_ids)),
                )
                for item in evidence
            )
            return AnswerResult(
                question=str(raw.get("question") or question),
                answer=str(raw.get("answer") or ""),
                plan=plan,
                evidence=evidence,
                citation_ids=citation_ids,
                trace=_trace(raw.get("trace") or ()),
                used_fallback=bool(raw.get("used_fallback")),
            )
        except (InvalidQueryError, ReasonerConfigurationError):
            raise
        except Exception as exc:
            raise ReasoningError(f"answering failed: {exc}") from exc
