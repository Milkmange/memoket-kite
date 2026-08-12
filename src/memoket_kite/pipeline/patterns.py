"""Shared question and answer patterns.

These predicates are consulted by retrieval, the answer stage and the
post-processing stage; keeping one definition prevents the three from
drifting apart.
"""

from __future__ import annotations

import re

#: Questions that ask the assistant for a judgement rather than for a fact.
#:
#: The distinction is a speech act, not a topic: "when did I buy the NAS" wants
#: a stored fact, while "should I buy a NAS now?" wants an opinion built on
#: stored facts. The refusal rules exist to catch a confident answer to a
#: question whose premise is absent; on a solicited judgement there is no
#: premise to be absent, so firing there destroys a correct answer.
#:
#: This is the library's generic predicate, covering the recommendation
#: vocabulary alone. A binding whose questions use a wider or domain-specific
#: request vocabulary supplies its own pattern through
#: ``profile.ADVICE_QUESTION`` (see ``benchmarks.common.policies``); every
#: consumer reaches the predicate through :func:`advice_predicate`, so the
#: override applies to retrieval, answering and post-processing at once.
ADVICE_QUESTION = re.compile(
    r"suggest|recommend|advice|tips|any ideas|help me"
    r"|\bwhat (should|would|do) (i|you)\b"
    r"|\bdo you think\b"
    r"|\bdo you have any (ideas|suggestions|tips|thoughts|recommendations|advice)\b",
    re.I,
)
#: Questions asking for a count.
COUNT_QUESTION = re.compile(r"几[段个次场条]|多少|how many|次数", re.I)
#: Answers that decline, beyond the literal refusal string.
REFUSAL_LIKE = re.compile(
    r"no information|not (specified|mentioned|stated|provided)|cannot be "
    r"determined|unknown|unclear from",
    re.I,
)
#: Indefinite answers that name a category instead of an instance.
VAGUE_ANSWER = re.compile(r"^(a|an|some)\s+[a-z][a-z\s,'-]{3,60}$", re.I)
#: Text whose meaning depends on when it was said.
RELATIVE_PHRASE = re.compile(
    r"\b(last|next)\s+(year|month|week|summer|winter|spring|fall)\b|"
    r"\b(a|two|three|few|several)\s+(days?|weeks?|months?|years?)\s+ago\b|"
    r"\byesterday\b|\btomorrow\b",
    re.I,
)


def advice_predicate(profile):
    """The advice predicate this binding runs.

    A profile may override :data:`ADVICE_QUESTION` with its own pattern.
    Everything in the pipeline that needs the predicate asks through here, so
    the override is resolved in one place and the generic library predicate is
    the fallback everywhere.
    """
    return getattr(profile, "ADVICE_QUESTION", None) or ADVICE_QUESTION
