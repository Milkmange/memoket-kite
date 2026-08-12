"""Offline unit tests for the deterministic post-processing rules (no LLM)."""

from memoket_kite.core.algebra import FactRecord, Store, Unit
from memoket_kite.pipeline import postproc
from memoket_kite.pipeline.verdicts import GateContext


def _store_with(texts):
    store = Store()
    for index, text in enumerate(texts):
        unit = f"u{index}"
        store.units.setdefault(unit, Unit(unit, "2023-05-01", "", "", 0, 0))
        record = FactRecord(
            id=f"f{index}",
            unit=unit,
            unit_date="2023-05-01",
            t="",
            kind="event",
            who="user",
            conf="med",
            topics=(),
            entities=(),
            src=(),
            text=text,
        )
        store.add_fact(record)
        store._index_text(text, key=("F", f"f{index}"))
    return store


def test_r2a_fires_only_on_premise_risk_confident_answers():
    store = _store_with(["moved into the Harajuku apartment"])
    risky = GateContext.build("How long in Shinjuku's apartment?", store)
    hit = postproc.premise_refusal(
        "How long in Shinjuku's apartment?",
        "You have lived there since March 2023.",
        risky,
    )
    assert hit is not None and hit[0] == postproc.CANONICAL_REFUSAL
    safe = GateContext.build("When did I move to Harajuku's apartment?", store)
    assert (
        postproc.premise_refusal(
            "When did I move to Harajuku's apartment?",
            "In March 2023.",
            safe,
        )
        is None
    )
    # already-refusal answers are untouched, and advice questions are exempt —
    # recognised from the question text, never from a dataset label
    assert postproc.premise_refusal("q", "No information", risky) is None
    assert postproc.premise_refusal("What should I cook this weekend?", "Answer.", risky) is None
    # the label alone must NOT exempt anything: a pipeline that reads the
    # benchmark's own question_type is a fork the system cannot defend
    assert postproc.premise_refusal("q", "Answer.", risky) is not None


def test_r2b_hedge_yet_asserts():
    hit = postproc.hedge_refusal(
        "Which project did I start first?",
        "You started the Ferrari model first; there is no evidence that you "
        "started the Porsche 991 Turbo S model.",
    )
    assert hit is not None and hit[0] == postproc.CANONICAL_REFUSAL
    pure_refusal = postproc.hedge_refusal("q", "There is no evidence about this.")
    assert pure_refusal is None  # hedge alone, nothing asserted
    clean_answer = postproc.hedge_refusal("q", "You started the Ferrari model on 2023-03-01.")
    assert clean_answer is None


def test_apply_rules_first_family_wins_and_logs():
    store = _store_with(["moved into the Harajuku apartment"])
    gate = GateContext.build("How long in Shinjuku's apartment?", store)
    answer, fired = postproc.apply_rules(
        "How long in Shinjuku's apartment?",
        "Since 2023-03-01, so 17 days as of 2023-03-13.",
        gate=gate,
        enable=frozenset({"premise", "hedge", "undercount", "zero"}),
    )
    assert answer == postproc.CANONICAL_REFUSAL
    assert [f["rule"] for f in fired] == ["premise_refusal"]


def test_r8_increments_only_against_a_saturated_basis():
    audit = {"instance_basis": 12, "answered": 2}
    hit = postproc.undercount_repair(
        "How many citrus fruits have I used?",
        "You have used 2 different types: lemon and lime.",
        audit,
    )
    assert hit is not None and hit[0] == "You have used 3 different types."
    assert (
        postproc.undercount_repair("How many X?", "2 things", {"instance_basis": 7, "answered": 2})
        is None
    )
    assert postproc.undercount_repair("Where did I go?", "2 places", audit) is None


def test_r9_appends_and_never_substitutes():
    hit = postproc.zero_disclosure("0 times")
    assert hit is not None and hit[0].startswith("0 times.")
    assert "not enough" in hit[0]
    assert postproc.zero_disclosure("You went 3 times") is None
    assert postproc.zero_disclosure("No information") is None


def test_a_spelled_count_is_read_from_where_it_appears_not_from_the_word_list():
    """ "three pieces ... one ring, one pair, one necklace" is three, not one."""
    from memoket_kite.pipeline.verdicts import _leading_count

    assert (
        _leading_count(
            "You acquired three pieces of jewelry: one engagement ring, "
            "one pair of earrings, and one silver necklace."
        )
        == 3
    )
    assert _leading_count("Twelve books and one magazine") == 12
    assert _leading_count("On 2023-05-13 you bought two items") == 2


def test_undercount_repair_rewrites_a_spelled_count_like_a_digit_one():
    """Surface form is not evidence, so the rule must not branch on it.

    "two" and "2" assert the same count with the same confidence, and the
    warrant for repairing either is the audit, not the spelling. Abstaining on
    the spelled form would leave exactly the same wrong answers standing in
    words. Case is carried across the rewrite so a sentence-initial count does
    not come back lowercased.
    """
    from memoket_kite.pipeline.postproc import undercount_repair

    audit = {"instance_basis": 12, "answered": 2}
    question = "How many different types of citrus fruits have I used?"

    digits, _ = undercount_repair(question, "You have used 2 different types.", audit)
    assert digits == "You have used 3 different types."
    spelled, _ = undercount_repair(question, "You have used two different types.", audit)
    assert spelled == "You have used three different types."
    leading, _ = undercount_repair(question, "Two types were used.", audit)
    assert leading == "Three types were used."


def test_undercount_repair_leaves_a_range_alone():
    """An endpoint is not a count, so incrementing it destroys the answer.

    "you need 2 to 3 eggs" satisfies every other test for a quantity — a noun
    follows it, it is not money and not a date — so without a range check the
    rule rewrites it to "3 to 3 eggs" and turns a correct answer into an
    incoherent one. The spread is recognised from the joiner that follows the
    number, in both digits and words.
    """
    from memoket_kite.pipeline.postproc import undercount_repair

    audit = {"instance_basis": 12, "answered": 2}
    question = "How many eggs do I need for the omelette?"

    for spread in (
        "You need 2 to 3 eggs.",
        "You need from 2 to 3 eggs.",
        "You need two or three eggs.",
        "You need 1 to 2 eggs.",
        "You need 2-3 eggs.",
        "You need between 2 and 3 eggs.",
        "You need between two and three eggs.",
    ):
        assert undercount_repair(question, spread, audit) is None, spread

    # A joiner only makes a range in front of another number, and "and" only
    # under "between" — "2 apples and 3 pears" is two counts, not a spread.
    for counted, expected in (
        ("You need 2 or more eggs.", "You need 3 or more eggs."),
        ("You bought 2 apples and 3 pears.", "You bought 3 apples and 3 pears."),
    ):
        repaired, _ = undercount_repair(question, counted, audit)
        assert repaired == expected


def test_both_surface_forms_get_the_same_guards():
    """A guard only one spelling gets is not a guard.

    Money and dates are the two places a number is not a count, and they occur
    written out as readily as in digits. A spelled branch that searches for the
    bare word skips those checks, so `two dollars worth of apples` becomes
    `three dollars worth` and `March two, 2023` becomes `March three`. Both
    surface forms run the same guards.
    """
    from memoket_kite.pipeline.postproc import undercount_repair

    audit = {"instance_basis": 12, "answered": 2}
    question = "How many did I buy?"

    for spelled, digits in (
        ("You bought two dollars worth of apples.", "You bought 2 dollars worth of apples."),
        ("You bought items on March two, 2023.", "You bought items on March 2, 2023."),
    ):
        assert undercount_repair(question, spelled, audit) is None, spelled
        assert undercount_repair(question, digits, audit) is None, digits


def test_undercount_repair_leaves_a_hedged_count_alone():
    """ "at least 2" already says the true number may be higher.

    Incrementing it does not repair an under-enumeration; it replaces one bound
    with another and asserts it just as confidently. The rule's warrant is a
    reader that committed to a count, and a hedged count is not a commitment.
    """
    from memoket_kite.pipeline.postproc import undercount_repair

    audit = {"instance_basis": 12, "answered": 2}
    question = "How many trips did I take?"

    for hedge in ("at least", "about", "around", "approximately", "over", "more than", "up to"):
        answer = f"You took {hedge} 2 trips."
        assert undercount_repair(question, answer, audit) is None, answer
    assert undercount_repair(question, "You took approximately two trips.", audit) is None
    # …while a bare commitment is still repaired
    repaired, _ = undercount_repair(question, "You took 2 trips.", audit)
    assert repaired == "You took 3 trips."
