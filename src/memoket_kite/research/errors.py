"""Exceptions raised by the KITE research API.

The research surface is intentionally separate from the stable public API and
its errors, so an application depending only on `memoket_kite` never has to know
these exist.
"""

from __future__ import annotations


class ResearchError(Exception):
    """Base class for errors raised by the research API."""


class CodebookLoadError(ResearchError):
    """A codebook artifact could not be loaded."""


class InvalidQueryError(ResearchError, ValueError):
    """A symbolic query or query plan is invalid."""


class ReasonerConfigurationError(ResearchError, ValueError):
    """A reasoner profile or model configuration is incomplete."""


class ReasoningError(ResearchError):
    """Natural-language retrieval or answering failed."""
