"""Advanced KITE interfaces for experiments and reproducible research.

Applications should use :class:`memoket_kite.Memory`. Names here retain the
former artifact-first API and may evolve with the research implementation.
"""

from memoket_kite.research.codebook import Codebook, CodebookInspector, Reasoner
from memoket_kite.research.errors import (
    CodebookLoadError,
    InvalidQueryError,
    ReasonerConfigurationError,
    ReasoningError,
    ResearchError,
)
from memoket_kite.research.profile import ReasonerProfile
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
    Sort,
    SourceLine,
    SymbolicQuery,
    TimeRange,
    TopicInfo,
    TopicMatch,
    TraceEvent,
)

__all__ = [
    "Aggregate",
    "AnswerResult",
    "Codebook",
    "CodebookInspector",
    "CodebookLoadError",
    "CodebookStats",
    "EntityInfo",
    "Evidence",
    "ExecutionTrace",
    "ResearchError",
    "InvalidQueryError",
    "QueryPlan",
    "QueryResult",
    "Reasoner",
    "ReasonerConfigurationError",
    "ReasonerProfile",
    "ReasoningError",
    "RetrievalResult",
    "Sort",
    "SourceLine",
    "SymbolicQuery",
    "TimeRange",
    "TopicInfo",
    "TopicMatch",
    "TraceEvent",
]
