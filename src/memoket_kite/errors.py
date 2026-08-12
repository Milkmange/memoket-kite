"""Errors raised by the public KITE Memory API.

One root, `KiteError`, so a caller can catch everything this library
raises with a single except clause — and so nothing this library raises is
ever confused with Python's built-in ``MemoryError``, which reports the
interpreter running out of memory, not a memory *system* misbehaving.
"""

from __future__ import annotations


class KiteError(Exception):
    """Base class for every error the KITE public API raises."""


class ConfigurationError(KiteError):
    """A model, provider, or profile configuration is missing or invalid."""


class StorageError(KiteError):
    """A memory artifact could not be read or written."""


class ProviderError(KiteError, RuntimeError):
    """The language-model provider failed or is not configured.

    Also a ``RuntimeError`` so the pipeline's existing ``except RuntimeError``
    retry and fallback handlers keep their behaviour: the provider boundary
    can carry its own public type without the internal layers changing.
    """


class QueryError(KiteError):
    """A question or symbolic query could not be compiled or executed."""
