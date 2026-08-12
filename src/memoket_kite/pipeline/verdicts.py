"""Deterministic, LLM-free verdicts about a question and its answer.

Two things live here, both consumed by the post-processing stage:

- ``GateContext`` — the premise gate. A question whose subject anchors have
  zero document frequency in the store asks about something memory has never
  seen; on a workload that contains unanswerable questions, that is a false
  premise rather than a retrieval failure.
- ``aggregation_audit`` — an under-enumeration signal for counting questions,
  computed against the instance index.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from memoket_kite.core.algebra import _tokens
from memoket_kite.pipeline.patterns import ADVICE_QUESTION

_POSSESSIVE = re.compile(r"\b([A-Z][a-z]{2,})'s\s+\w+")
# Maximal capitalized runs ("Porsche 991 Turbo S", "Shinjuku") — the dominant
# premise-anchor shape on first-person questions, where possessives are rare.
_PROPER_RUN = re.compile(r"\b[A-Z][a-z]{2,}(?:\s+[A-Z][a-z0-9]{1,})*\b")
# Weekday, month and relative-time words are held structurally rather than as
# fact text, so their document frequency is always zero and says nothing about
# whether a question's premise holds. Stemmed with the same tokenizer the
# lookup uses, or the longer names would never match.
_TIME_WORD_STEMS = frozenset(
    _tokens(
        "monday tuesday wednesday thursday friday saturday sunday january"
        " february march april may june july august september october november"
        " december today tomorrow yesterday weekend"
    )
)
_QUESTION_STARTERS = frozenset(
    "what when where which who whom whose how why did do does have has had was"
    " were is are am can could would should will the".split()
)


def _stem_df(stem: str, store) -> int:
    return len(getattr(store, "by_token", {}).get(stem, ()) or ())


@dataclass
class GateContext:
    """Per-question premise-gate state, computed once, LLM-free."""

    subjects: list[str] = field(default_factory=list)
    premise_risk: bool = False

    @classmethod
    def build(cls, question: str, store, intent: str = "", advice=None) -> "GateContext":
        subjects: list[str] = []
        seen: set[str] = set()
        # Subjects come from the question text alone, not from the compiled
        # plan: plan entities live inside each query and never at the top
        # level, so a top-level plan lookup yields an empty subject list.
        candidates = _POSSESSIVE.findall(question or "")
        for match in _PROPER_RUN.finditer(question or ""):
            if match.start() == 0:
                continue  # sentence-initial capitalization is not a name
            candidates.append(match.group(0))
        for name in candidates:
            key = name.strip().lower()
            if not key or key in seen or key in _QUESTION_STARTERS:
                continue
            seen.add(key)
            subjects.append(name.strip())
        risk = False
        for subject in subjects:
            stems = [
                stem for stem in _tokens(subject) if len(stem) >= 3 and stem not in _TIME_WORD_STEMS
            ]
            if stems and all(_stem_df(stem, store) == 0 for stem in stems):
                risk = True
                break
        # Intent conditioning: a missing entity is evidence of a false premise
        # only on factual and retrospective questions, which assert that the
        # entity exists in memory. Speculative and advice questions instead
        # supply the entity themselves ("would Tim enjoy C.S. Lewis?"), so its
        # absence from the store is expected and carries no premise signal.
        if risk and (intent == "speculative" or (advice or ADVICE_QUESTION).search(question or "")):
            risk = False
        return cls(subjects=subjects, premise_risk=risk)


_DURATION_Q = re.compile(
    r"how\s+(?:many|much)\s+(?:days?|weeks?|months?|hours?|minutes?|years?"
    r"|money|time)|how\s+long|\bago\b|\bbetween\b|\bpassed\b|\bsave\b|\$",
    re.I,
)
# Shared with the post-processing repair: a count the audit can read must
# also be one the repair can rewrite.
SPELLED_COUNTS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _leading_count(answer_text: str) -> int | None:
    """First count-like number: skips dates, fractions/model numbers, and
    comma-formatted amounts; falls back to spelled numbers. The obvious
    ``\\b\\d{1,3}\\b`` regex is not used because it parses '2023-05-13' as 5."""
    text = answer_text or ""
    for match in re.finditer(r"\d+(?:\.\d+)?", text):
        token = match.group(0)
        before = text[max(0, match.start() - 1) : match.start()]
        after = text[match.end() : match.end() + 1]
        if before in ("-", "/", ",", ".", "$") or after in ("-", "/", ","):
            continue  # date fragment, fraction/model number, currency mass
        if len(token) == 4 and token.startswith(("19", "20")):
            continue  # year
        if "." in token:
            continue
        value = int(token)
        if value <= 400:
            return value
    # One alternation over the text, so the match is the earliest spelled
    # number IN THE TEXT. Iterating SPELLED_COUNTS instead would report the
    # lowest-valued spelled number appearing anywhere, reading "three pieces
    # ... one ring, one pair, one necklace" as a count of one.
    spelled = re.search(rf"\b({'|'.join(SPELLED_COUNTS)})\b", text, re.I)
    return SPELLED_COUNTS[spelled.group(1).lower()] if spelled else None


def aggregation_audit(
    answer_text: str,
    intent: str,
    instances: list[dict],
    *,
    question: str = "",
    refusal_like: re.Pattern | None = None,
) -> dict | None:
    """What the answer counted, against how many instances were available.

    This verdict does not act. It is recorded on the result, and a deployment
    that enables the `undercount` post-processing rule may then read it — the
    answer stage itself never escalates on it, because the instance index is a
    keyword-scored top-12 rather than a criteria lower bound, so `undercount`
    here means "worth a second look", not "provably too low". Anything reading
    it inherits that limit: see `postproc.undercount_repair`, which is why
    that rule demands a saturated basis before it will touch an answer.

    Hard guards: never fire on duration/measure questions, refusal-shaped or
    hedged answers, zero answers, or an absent basis."""
    if intent not in ("aggregate", "enumeration") or not instances:
        return None
    if _DURATION_Q.search(question or ""):
        return None
    text = (answer_text or "").strip()
    if not text or (refusal_like is not None and refusal_like.search(text)):
        return None
    answered = _leading_count(text)
    if answered is None or answered == 0:
        return None
    basis = len(instances)
    return {"answered": answered, "instance_basis": basis, "undercount": answered < basis}
