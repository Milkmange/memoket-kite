"""Offline unit tests (no LLM) for the channel ledger and the premise gate."""

from memoket_kite.core.algebra import FactRecord, Store, Unit
from memoket_kite.pipeline import ledger, verdicts


def _fact(store, fid, unit, text, who="a"):
    store.units.setdefault(unit, Unit(unit, "2026-01-01", "", "", 0, 0))
    record = FactRecord(
        id=fid,
        unit=unit,
        unit_date="2026-01-01",
        t="",
        kind="event",
        who=who,
        conf="med",
        topics=(),
        entities=(),
        src=(),
        text=text,
    )
    if store.add_fact(record):
        store._index_text(record.text, key=("F", fid))


# ---------------------------------------------------------------------------
# The channel ledger


def test_ledger_is_inert_when_inactive():
    ledger.end()  # ensure no active ledger
    ledger.charge("row_renders", compact=100, real=200)
    ledger.call("answer", "prompt text")
    assert ledger.current() is None
    assert ledger.snapshot() is None


def test_ledger_books_channels_and_calls():
    ledger.begin()
    ledger.charge("row_renders", compact=100, real=250, n=5)
    ledger.charge("neighbor_context", real=90)
    ledger.charge("row_renders", compact=10, real=20, n=1)
    ledger.call("answer", "word " * 100)
    ledger.note("premise", {"risk": False})
    snap = ledger.snapshot()
    ledger.end()
    assert snap["channels"]["row_renders"] == {"compact": 110, "real": 270, "n": 6}
    assert snap["channels"]["neighbor_context"]["real"] == 90
    assert snap["compact_total"] == 110
    assert snap["real_total"] == 360
    assert snap["call_total"] == 1
    assert snap["reader_calls"][0]["site"] == "answer"
    assert snap["prompt_tokens_max"] > 0
    assert snap["notes"]["premise"] == {"risk": False}
    assert ledger.current() is None  # end() clears the slot


# ---------------------------------------------------------------------------
# Premise-gate context


def test_subjects_come_from_the_question_alone():
    """The gate reads the question, not the compiled plan.

    A compiled plan carries entities per query and never at the top level, so a
    subject set drawn from `plan["entities"]` is always empty: it would read as
    "no subjects to check" and silence the gate rather than widen it.
    """
    store = Store()
    gate = verdicts.GateContext.build(
        "How long have I been living in Marcus's apartment?",
        store,
    )
    assert "Marcus" in gate.subjects


def test_premise_risk_fires_only_on_zero_df_subjects():
    store = Store()
    _fact(store, "f1", "u1", "moved into the Harajuku apartment in March")
    known = verdicts.GateContext.build("When did I move into Harajuku's apartment?", store)
    assert not known.premise_risk
    absent = verdicts.GateContext.build("How long have I lived in Shinjuku's apartment?", store)
    assert absent.premise_risk
