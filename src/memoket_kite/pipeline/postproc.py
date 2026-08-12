"""Deterministic answer post-processing: zero-LLM symbolic repairs.

Every rule is gold-blind — it reads only the question text, the answer's own
text, and the deterministic verdicts the answer stage recorded (premise gate,
aggregation audit). No rule inspects question ids, benchmark labels, gold
answers, or judge output. Which rules a deployment enables is declared in its
binding and published with the results.

The rules:

- premise refusal — a factual question whose subject anchors are absent from
  memory is answered with the canonical refusal; never fires where the
  workload declares questions answerable by construction.
- hedge canonicalization — an answer that asserts while stating the evidence
  is absent becomes the canonical refusal.
- saturated-basis undercount — a counting answer far below a saturated
  instance basis is incremented.
- zero-answer disclosure — a bare leading zero gets an explicit not-found
  clause appended, never substituted.

Deliberately out of scope: date arithmetic (a wrong date is an
anchor-selection failure upstream, not an arithmetic one), value substitution
on knowledge updates, turning a refusal back into an assertion, and
count-consistency rewrites. Each of those would have to invent content that
does not follow from the question, the answer text, and the recorded
verdicts, which is the only material a rule here is allowed to read.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from memoket_kite.pipeline import verdicts
from memoket_kite.pipeline.patterns import ADVICE_QUESTION, REFUSAL_LIKE

CANONICAL_REFUSAL = "No information"

# Phrases with which an answer states, about its own evidence, that there is
# none. The lexicon is closed on purpose: it is the trigger for rewriting an
# answer into a refusal, so every phrase admitted here has to be unambiguous.
_HEDGE = re.compile(
    r"there is no (evidence|information|record)|no (evidence|information) "
    r"(that|about|of)|it is not (mentioned|specified|stated)",
    re.I,
)


def premise_refusal(
    question: str,
    answer: str,
    gate,
    answerable: bool = False,
    advice: "re.Pattern | None" = None,
) -> tuple[str, dict] | None:
    """Absent-entity factual question answered confidently -> refusal.

    Never fires when the deployment declares the question answerable by
    construction: every question in such a workload has an answer somewhere in
    memory, so a refusal there is a guaranteed miss."""
    if answerable:
        return None
    # Advice questions are recognised from the question text alone. A dataset
    # label such as `single-session-preference` carries the same signal, but it
    # is annotation the benchmark ships rather than anything a deployment holds
    # at inference time, so no branch here may read one.
    # `tests/unit/test_bindings.py` fails if any benchmark label reaches here.
    if (advice or ADVICE_QUESTION).search(question or ""):
        return None
    if gate is None or not gate.premise_risk:
        return None
    if REFUSAL_LIKE.search(answer or "") or not (answer or "").strip():
        return None
    return CANONICAL_REFUSAL, {
        "rule": "premise_refusal",
        "subjects": list(gate.subjects),
    }


def hedge_refusal(
    question: str,
    answer: str,
    answerable: bool = False,
    advice: "re.Pattern | None" = None,
) -> tuple[str, dict] | None:
    """Answer asserts while itself declaring the evidence absent -> refusal.

    Like the premise rule, this never fires where the workload declares the
    question answerable by construction."""
    if answerable:
        return None
    # See `premise_refusal`: recognised from the question, never from a
    # dataset label.
    if (advice or ADVICE_QUESTION).search(question or ""):
        return None
    text = (answer or "").strip()
    if not text or len(text) < 40:
        return None
    hedge = _HEDGE.search(text)
    if not hedge:
        return None
    # "asserts": the hedge is not the whole answer — substantive content
    # (>= 25 chars) exists outside the hedge sentence.
    remainder = (text[: hedge.start()] + text[hedge.end() :]).strip(" .,;—-")
    if len(remainder) < 25 or REFUSAL_LIKE.match(text):
        return None
    return CANONICAL_REFUSAL, {"rule": "hedge_refusal", "hedge": hedge.group(0)}


def apply_rules(
    question: str,
    answer: str,
    *,
    gate=None,
    audit: dict | None = None,
    answerable: bool = False,
    enable: frozenset[str] = frozenset(),
    advice: "re.Pattern | None" = None,
) -> tuple[str, list[dict]]:
    """Apply the enabled rules in a fixed order.

    The two refusal rules are mutually exclusive — once one has rewritten the
    answer the other is skipped — while the counting repair and the zero
    disclosure are independent of them."""
    fired: list[dict] = []
    current = answer
    if "premise" in enable:
        hit = premise_refusal(question, current, gate, answerable=answerable, advice=advice)
        if hit:
            current, log = hit
            fired.append(log)
    if "hedge" in enable and not fired:
        hit = hedge_refusal(question, current, answerable=answerable, advice=advice)
        if hit:
            current, log = hit
            fired.append(log)
    if "undercount" in enable:
        hit = undercount_repair(question, current, audit)
        if hit:
            current, log = hit
            fired.append(log)
    if "zero" in enable and not fired:
        hit = zero_disclosure(current)
        if hit:
            current, log = hit
            fired.append(log)
    return current, fired


@dataclass(frozen=True)
class _PremiseVerdict:
    """The premise-gate verdict as the answer stage recorded it."""

    subjects: list[str]
    premise_risk: bool


def apply_to_record(
    record: dict,
    telemetry: dict | None,
    enable: frozenset[str],
    advice: "re.Pattern | None" = None,
):
    """Harness-level entry point: apply enabled rules to one result record.

    Reads the premise verdict the answer stage recorded, so post-processing
    stays a separable stage outside the answer flow. Returns the rewritten
    answer and the log of rules that fired."""
    if not enable:
        return record.get("answer", ""), []
    recorded = ((telemetry or {}).get("notes") or {}).get("premise") or {}
    verdict = {
        "subjects": list(recorded.get("subjects") or []),
        "premise_risk": bool(recorded.get("risk")),
    }
    return apply_rules(
        record.get("question", ""),
        record.get("answer", ""),
        gate=_PremiseVerdict(**verdict) if recorded else None,
        audit=((telemetry or {}).get("notes") or {}).get("aggregation_audit"),
        answerable=bool(record.get("answerable_by_construction")),
        enable=enable,
        advice=advice,
    )


# Every name `apply_rules` dispatches on. `rules_from_env` rejects anything
# outside this set, so a misspelled name raises instead of parsing cleanly into
# a rule that then never matches.
RULES = frozenset({"premise", "hedge", "undercount", "zero"})


def rules_from_env(value: str | None) -> frozenset[str]:
    """Parse KITE_POSTPROC ("premise,zero") into an enabled-rule set."""
    named = frozenset(part.strip().lower() for part in (value or "").split(",") if part.strip())
    if unknown := sorted(named - RULES):
        raise ValueError(f"unknown post-processing rule(s): {', '.join(unknown)}")
    return named


# ---------------------------------------------------------------------------
# Rules that read the answer stage's own telemetry rather than the answer alone.

_HOW_MANY = re.compile(r"\bhow many\b", re.I)
_LEADING_ZERO = re.compile(r"^\s*(0|zero)\b", re.I)
_NOT_FOUND_CLAUSE = (
    " I could not find any record of this in the stored history, so the "
    "information provided is not enough to answer this question."
)


#: A count is followed by the thing it counts.
_NAMES_WHAT_IT_COUNTS = re.compile(r"\s+[A-Za-z]")
_MONTHS = "january|february|march|april|may|june|july|august|september|october|november|december"
#: …and it is preceded by neither a currency symbol nor a month name.
_NOT_A_COUNT = re.compile(rf"[$£€#]\s*$|\b(?:{_MONTHS})\s+$", re.I)
#: Spelled money reads the other way round: "$2" puts the symbol in front,
#: "two dollars" puts the unit behind, so the trailing unit needs its own test.
_CURRENCY_AFTER = re.compile(r"\s*(?:dollars?|euros?|pounds?|cents?|yen|yuan|usd|eur|gbp)\b", re.I)
#: "Two days ago" counts nothing — it locates something in time. The time unit
#: alone does not settle it, because "2 days" is a fine answer to "how many
#: days"; the relative marker after the unit is what makes it a reference.
_TIME_REFERENCE = re.compile(
    r"\s*(?:seconds?|minutes?|hours?|days?|weeks?|months?|years?|decades?)\s+"
    r"(?:ago|later|earlier|before|after|prior|from now|from then)\b",
    re.I,
)
#: A count the reader qualified is not one it committed to. "at least 2" is
#: already an admission that the true number may be higher, so incrementing it
#: does not repair an under-enumeration — it invents a different bound and
#: states it just as confidently.
_HEDGED_COUNT = re.compile(
    r"\b(?:at least|at most|about|around|approximately|roughly|nearly|almost|over|under|"
    r"more than|less than|fewer than|up to)\s+$",
    re.I,
)
_NUMBER = rf"\d+|(?:{'|'.join(verdicts.SPELLED_COUNTS)})"
#: A range states a spread, not a count: incrementing an endpoint of "2 to 3
#: eggs" yields "3 to 3 eggs", which is not even a range. Both ends are
#: rejected, in digits and in words.
_JOINER = r"to|or|through|[-–—]"
_RANGE_AFTER = re.compile(rf"\s*(?:{_JOINER})\s*(?:{_NUMBER})\b", re.I)
_RANGE_BEFORE = re.compile(rf"\b(?:{_NUMBER})\s*(?:{_JOINER})\s*$", re.I)
#: "and" joins a range only under "between". Alone it joins two separate
#: counts — "2 apples and 3 pears" — so it is the opening "between" that makes
#: the phrase a range, and each end is recognised from its own side of it.
_BETWEEN_LOWER = re.compile(r"\bbetween\s+$", re.I)
_BETWEEN_UPPER = re.compile(rf"\bbetween\s+(?:{_NUMBER})\s+and\s+$", re.I)
_AND_NUMBER = re.compile(rf"\s*and\s+(?:{_NUMBER})\b", re.I)


def _reads_as_range(before: str, after: str) -> bool:
    """Whether the number between these two sides is an endpoint of a range."""
    if _RANGE_AFTER.match(after) or _RANGE_BEFORE.search(before):
        return True
    if _BETWEEN_LOWER.search(before) and _AND_NUMBER.match(after):
        return True
    return bool(_BETWEEN_UPPER.search(before))


def _quantity_occurrence(answer: str, token: str) -> re.Match | None:
    """The occurrence of `token` that reads as a plain, committed quantity.

    Both branches of the repair — the digit form and the spelled form — resolve
    their target through this one function, so every guard below applies to
    both surface forms. A guard applied to only one of them is no guard at all:
    the number in `two dollars worth of apples` or in `March two, 2023` is as
    ineligible for incrementing as its digit spelling would be.
    """
    for match in re.finditer(rf"\b{token}\b", answer, re.I):
        before = answer[: match.start()]
        after = answer[match.end() :]
        # A count names what it counts. Cheapest test, and it subsumes every
        # date of the form "May 2, 2023" on its own — a comma is not a word —
        # so there is no separate year check to keep in step with this one.
        if not _NAMES_WHAT_IT_COUNTS.match(after):
            continue
        if _NOT_A_COUNT.search(before) or _HEDGED_COUNT.search(before):
            continue
        if _CURRENCY_AFTER.match(after) or _TIME_REFERENCE.match(after):
            continue
        if _reads_as_range(before, after):
            continue
        return match
    return None


def undercount_repair(
    question: str,
    answer: str,
    audit: dict | None,
    *,
    basis_floor: int = 11,
    answered_ceiling: int = 2,
) -> tuple[str, dict] | None:
    """Under-enumeration repair on a SATURATED instance basis.

    The instance index is a keyword-scored list capped at 12 entries; a basis
    at or above ``basis_floor`` means the cap is effectively saturated, i.e.
    many candidates matched. A reader that commits to <= ``answered_ceiling``
    against a saturated basis has usually under-enumerated. The repair
    increments by one — the smallest correction consistent with
    "under-enumerated" — and drops any enumeration clause the count no longer
    matches.

    The firing condition does not depend on how the answer spells its count, so
    digits and words are handled alike: refusing one surface form would decline
    repairs without narrowing the condition under which the rule fires. See
    `tests/unit/test_postproc.py` for the pinned cases."""
    if not audit or not _HOW_MANY.search(question or ""):
        return None
    basis = int(audit.get("instance_basis") or 0)
    answered = int(audit.get("answered") or 0)
    if basis < basis_floor or not 0 < answered <= answered_ceiling:
        return None
    # The audit reads spelled numbers ("two" -> 2), so the repair has to write
    # them too: a search for the digit alone would skip every answer that
    # spells its count, and the digit branch is tried first only because it is
    # the cheaper of the two.
    #
    # It must rewrite the COUNT, though, and an answer contains other numbers.
    # A bare search for the digit would hit the amount in "you spent $2 and
    # took 2 trips" and the day in "2 trips in May 2, 2023", so a candidate is
    # rejected unless it reads as a quantity: not a price, not a day of a
    # month, not a year, and followed by the thing being counted.
    match = _quantity_occurrence(answer or "", str(answered))
    if match:
        replacement = str(answered + 1)
    else:
        spelled = {value: word for word, value in verdicts.SPELLED_COUNTS.items()}
        if (word := spelled.get(answered)) is None:
            return None
        match = _quantity_occurrence(answer or "", word)
        if not match:
            return None
        replacement = spelled.get(answered + 1, str(answered + 1))
        if match.group(0)[:1].isupper():
            replacement = replacement.capitalize()
    repaired = answer[: match.start()] + replacement + answer[match.end() :]
    # An enumeration that follows the count no longer matches it, so it goes.
    # Only a colon at or after the count qualifies: a colon can also introduce
    # the answer itself ("Answer: 2 trips to the coast"), and cutting there
    # would leave the label with nothing after it.
    tail = repaired.find(":", match.start())
    if tail != -1:
        repaired = repaired[:tail].rstrip(" ,;") + "."
    return repaired, {
        "rule": "undercount_repair",
        "answered": answered,
        "repaired_to": answered + 1,
        "instance_basis": basis,
    }


def zero_disclosure(answer: str) -> tuple[str, dict] | None:
    """Append-only disclosure when the answer opens with a bare zero count.

    A leading "0"/"zero" means the reader searched and found nothing, which is
    an absence-of-evidence statement rather than a counted zero. The clause is
    appended, never substituted, so no content is destroyed."""
    text = (answer or "").strip()
    if not text or not _LEADING_ZERO.match(text):
        return None
    if "not enough" in text.lower() or REFUSAL_LIKE.search(text):
        return None
    return text.rstrip(" .") + "." + _NOT_FOUND_CLAUSE, {"rule": "zero_disclosure"}
