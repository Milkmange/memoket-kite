from pathlib import Path

from memoket_kite.core.algebra import Store, execute_plan

DEMO = Path(__file__).parents[2] / "examples" / "data" / "demo_codebook.xml"


def test_golden_entity_plan_and_trace_are_stable():
    store, vocab = Store.load([str(DEMO)])
    plan = {
        "queries": [
            {
                "select": "facts",
                "where": {"entities": ["shanghai"]},
            }
        ],
        "intent": "factual",
    }

    rows, trace = execute_plan(store, vocab, plan, speakers=store.speakers)

    assert [(row["id"], row["date"]) for row in rows] == [("s2F1", "2026-10")]
    assert [stage["stage"] for stage in trace.stages] == ["expand", "refine", "pack"]
    assert trace.stages[0] == {"stage": "expand", "atom": "entities", "hits": 1}
