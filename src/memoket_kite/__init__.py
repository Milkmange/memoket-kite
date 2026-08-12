"""KITE: symbolic long-term memory for conversational agents.

KITE — Knowledge-Indexed Temporal Evidence: conversations settle into typed,
dated facts; questions compile into inspectable symbolic plans; answers carry
the evidence they stand on.
"""

from __future__ import annotations

from memoket_kite.errors import (
    ConfigurationError,
    KiteError,
    ProviderError,
    QueryError,
    StorageError,
)
from memoket_kite.fact import Answer, Fact
from memoket_kite.memory import Memory

__version__ = "0.1.0"

__all__ = [
    "Memory",
    "Fact",
    "Answer",
    "KiteError",
    "ConfigurationError",
    "StorageError",
    "ProviderError",
    "QueryError",
    "__version__",
]
