from pathlib import Path

from memoket_kite.core.algebra import Store

DEMO = Path(__file__).parents[2] / "examples" / "data" / "demo_codebook.xml"


def test_demo_codebook_loads_all_structures():
    store, vocab = Store.load([str(DEMO)])

    assert set(store.units) == {"s1", "s2"}
    assert set(store.facts) == {"s1F1", "s2F1"}
    assert store.facts["s1F1"].when == "2026-10-18"
    assert store.lines["s1L1"].text.startswith("I started training")
    assert vocab.downset("activities") == {"activities", "marathon_training"}
    assert vocab.entities["shanghai"].etype == "place"


def test_a_model_supplied_blank_symbol_never_reaches_disk(tmp_path):
    """A whitespace- or punctuation-only topic or entity name normalises to the
    empty string, and an empty code written out as <topic code=""> is valid XML
    that the loader refuses in BOTH strict and lenient mode. One such proposal
    would therefore make the user's only durable memory file permanently
    unopenable, so a symbol that normalises to nothing is dropped before the
    write rather than rejected on the next read.
    """
    import shutil
    from unittest.mock import patch

    import memoket_kite.memory as memory_module
    import memoket_kite.pipeline.extract as extract_module
    from memoket_kite import Memory

    source = Path(__file__).resolve().parents[2] / "examples/data/demo_codebook.xml"
    for label, payload in (
        ("topic", {"proposals": [{"code": " ", "parent": "activities"}], "facts": []}),
        (
            "entity",
            {
                "proposals": [],
                "facts": [
                    {
                        "t": "2026-01-01",
                        "kind": "event",
                        "text": "x",
                        "src": ["s9:0"],
                        "entities": ["..."],
                    }
                ],
            },
        ),
    ):
        path = tmp_path / f"{label}.xml"
        shutil.copy(source, path)
        with (
            patch.object(extract_module, "llm_json", return_value=payload),
            patch.object(memory_module, "ensure_configured", lambda *a, **k: None),
        ):
            Memory.load(str(path)).remember([{"role": "user", "content": "hello"}], session_id="s9")
        assert 'code=""' not in path.read_text(encoding="utf-8")
        Memory.load(str(path))  # must still open


def test_a_second_writer_cannot_delete_the_first_writers_symbols(tmp_path):
    """Two Memory instances loaded from the same file: the second holds a
    vocabulary from before the first wrote. Writing that stale vocabulary back
    wholesale would delete the first writer's topic while keeping the Facts
    that reference it, so the write checks that the file has not moved since it
    was loaded and refuses instead.
    """
    import shutil
    from unittest.mock import patch

    import pytest

    import memoket_kite.memory as memory_module
    import memoket_kite.pipeline.extract as extract_module
    from memoket_kite import Memory
    from memoket_kite.errors import StorageError

    source = Path(__file__).resolve().parents[2] / "examples/data/demo_codebook.xml"
    path = tmp_path / "shared.xml"
    shutil.copy(source, path)
    with patch.object(memory_module, "ensure_configured", lambda *a, **k: None):
        first, second = Memory.load(str(path)), Memory.load(str(path))
        with patch.object(
            extract_module,
            "llm_json",
            return_value={
                "proposals": [{"code": "alpha_topic", "parent": "activities"}],
                "facts": [],
            },
        ):
            first.remember([{"role": "user", "content": "a"}], session_id="sA")
        with (
            patch.object(
                extract_module,
                "llm_json",
                return_value={
                    "proposals": [{"code": "beta_topic", "parent": "activities"}],
                    "facts": [],
                },
            ),
            pytest.raises(StorageError, match="changed since it was loaded"),
        ):
            second.remember([{"role": "user", "content": "b"}], session_id="sB")
    assert 'code="alpha_topic"' in path.read_text(encoding="utf-8")
