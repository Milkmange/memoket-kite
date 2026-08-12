"""The structured results returned by the public Memory API."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from memoket_kite.research.query import Evidence as StoredEvidence


def _freeze(value: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(copy.deepcopy(dict(value)))


@dataclass(frozen=True)
class Fact:
    """One structured memory fact with its supporting utterances."""

    id: str
    content: str
    kind: str | None = None
    subject: str | None = None
    topics: tuple[str, ...] = ()
    entities: tuple[str, ...] = ()
    event_time: str | None = None
    source_time: str | None = None
    confidence: str | None = None
    sources: tuple[Mapping[str, str | None], ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "topics", tuple(self.topics))
        object.__setattr__(self, "entities", tuple(self.entities))
        object.__setattr__(self, "sources", tuple(_freeze(source) for source in self.sources))
        object.__setattr__(self, "metadata", _freeze(self.metadata))


def fact_from_stored(item: "StoredEvidence") -> Fact:
    """Hydrate a public Fact from the research retrieval representation."""
    sources = tuple(
        {
            "id": source.id,
            "role": source.subject,
            "content": source.text,
            "date": source.source_time or None,
        }
        for source in item.sources
    )
    metadata = {
        "unit_id": item.unit_id,
        "source_ids": item.source_ids,
        "score": item.score,
        "cited": item.cited,
        **dict(item.attributes),
    }
    return Fact(
        id=item.id,
        content=item.text,
        kind=item.kind,
        subject=item.subject,
        topics=item.topics,
        entities=item.entities,
        event_time=item.event_time,
        source_time=item.source_time,
        confidence=item.confidence,
        sources=sources,
        metadata=metadata,
    )


@dataclass(frozen=True)
class Answer:
    """An answer together with the evidence it stands on.

    ``text`` alone is what ``Memory.answer`` returns; this object is for
    callers who need an auditable result — the retrieved Facts and the
    provenance IDs the reader cited. A citation may name a Fact, a raw source
    line, or a deduplicated instance rendered in the evidence pack. Raw lines
    and instances are intentionally not coerced into ``Fact`` objects, so
    their IDs can appear in ``citations`` without a matching item in
    ``evidence``. Evidence is the retrieved basis for the answer, not a proof
    of it: the reader chose its words, and the receipts record what it saw.
    """

    question: str
    text: str
    evidence: tuple[Fact, ...] = ()
    citations: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence", tuple(self.evidence))
        object.__setattr__(self, "citations", tuple(self.citations))
