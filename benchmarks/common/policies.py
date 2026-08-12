"""Question predicates the benchmark bindings inject.

The library ships a narrow advice predicate; a binding that wants a wider one
injects it from here. That keeps the boundary between library and benchmark a
file boundary rather than a convention: every pipeline consumer reads
``profile.ADVICE_QUESTION`` and falls back to the library predicate, and each
run manifest records the digest of the predicate a score ran under.
"""

from __future__ import annotations

import re

from memoket_kite.pipeline.patterns import ADVICE_QUESTION as GENERIC_ADVICE_QUESTION

#: Judgement-seeking phrasings the library predicate does not cover. It keys on
#: explicit speech acts ("recommend", "suggest", "advise"); these ask for an
#: opinion without using one. Matching reads the question text alone: never an
#: identifier, a gold answer, or judge output.
PROTOCOL_ADVICE_FAMILIES = (
    r"\bwould it be\b|\bis it (a )?good idea\b|\bworth (it|doing|buying|trying)\b"
    r"|\bcould there be\b|\bany (thoughts|reason)\b"
)

#: The predicate both bindings run: the library's speech-act vocabulary plus the
#: families above, composed so the relationship stays visible in the pattern
#: itself rather than being asserted in prose.
PROTOCOL_ADVICE_QUESTION = re.compile(
    GENERIC_ADVICE_QUESTION.pattern + "|" + PROTOCOL_ADVICE_FAMILIES,
    re.I,
)
