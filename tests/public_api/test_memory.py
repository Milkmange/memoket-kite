"""Contract tests for the small application-facing Memory API."""

import importlib.util
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from memoket_kite import Fact, KiteError, Memory
from memoket_kite.core.vocab import Vocab

DEMO = Path(__file__).parents[2] / "examples" / "data" / "demo_codebook.xml"


def _fact(identifier: str = "s1F1") -> Fact:
    return Fact(
        id=identifier,
        content="Alice likes trail running.",
        subject="alice",
        topics=("activities",),
        sources=(
            {
                "id": "s1L1",
                "role": "alice",
                "content": "I like running.",
                "date": "2026-01-10",
            },
        ),
    )


def test_memory_uses_a_default_model_and_accepts_an_override():
    memory = Memory.load(DEMO)
    assert memory is not None
    assert memory._model == "gpt-4.1-mini"
    assert Memory.load(DEMO, model="test:model")._model == "test:model"
    assert (
        Memory.load(DEMO, reference_date=datetime(2026, 8, 11, 23, 59))._reference_date
        == "2026-08-11"
    )
    with pytest.raises(KiteError, match="valid ISO date"):
        Memory.load(DEMO, reference_date="2026-02-31")
    with pytest.raises(KiteError, match="ISO date"):
        Memory.load(DEMO, reference_date="not-a-date")


def test_recall_and_answer_return_the_simple_contract(monkeypatch):
    memory = Memory.load(DEMO, model="test:model")

    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)

    monkeypatch.setattr("memoket_kite.memory.fact_from_stored", lambda fact: fact)
    stored_fact = SimpleNamespace(type="fact", **_fact().__dict__)
    stored_line = SimpleNamespace(type="line", id="s1L1")  # must NOT surface as a Fact
    monkeypatch.setattr(
        memory,
        "_reasoner",
        lambda: SimpleNamespace(
            retrieve=lambda *args, **kwargs: SimpleNamespace(evidence=(stored_fact, stored_line)),
            answer=lambda *args, **kwargs: SimpleNamespace(
                question="What does Alice like?",
                answer="Alice likes trail running.",
                evidence=(stored_fact, stored_line),
                citation_ids=("s1L1",),
            ),
        ),
    )

    facts = memory.recall("What does Alice like?")
    assert isinstance(facts, list)
    # The raw line was retrieved too, but a line is not a fact: exactly one
    # Fact comes back, and nothing with type="line" is dressed up as one.
    assert len(facts) == 1
    assert facts[0].content == "Alice likes trail running."
    with pytest.raises(TypeError):
        facts[0].metadata["kind"] = "changed"
    with pytest.raises(TypeError):
        facts[0].sources[0]["content"] = "changed"

    assert memory.answer("What does Alice like?") == "Alice likes trail running."

    result = memory.answer_with_evidence("What does Alice like?")
    assert result.text == "Alice likes trail running."
    assert result.question == "What does Alice like?"
    assert result.citations == ("s1L1",)
    assert len(result.evidence) == 1 and result.evidence[0].content == facts[0].content


def test_memory_validates_questions_and_multi_shard_writes():
    memory = Memory.load(DEMO, model="test:model")
    for bad_limit in (0, -1, True):
        with pytest.raises(KiteError, match="limit"):
            memory.recall("question", limit=bad_limit)
    with pytest.raises(KiteError, match="question"):
        memory.answer(" ")

    sharded = Memory.load([DEMO, DEMO], model="test:model")
    with pytest.raises(KiteError, match="exactly one"):
        sharded.remember([("alice", "Hello")])


def test_remember_appends_a_session_and_refreshes_memory(tmp_path, monkeypatch):
    path = tmp_path / "memory.xml"
    path.write_bytes(DEMO.read_bytes())
    memory = Memory.load(path, model="test:model")
    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)

    extraction_modes = []

    def fake_extract(vocab, session, model, include_facets):
        extraction_modes.append(include_facets)
        return [
            {
                "content": "Alice likes trail running.",
                "kind": "preference",
                "who": "alice",
                "t": "",
                "conf": "high",
                "topics": (),
                "entities": (),
                "src": [f"{session['id']}L1"],
                "obj": ["activity"],
            }
        ]

    monkeypatch.setattr("memoket_kite.memory.extract_facts", fake_extract)

    created = memory.remember(
        [{"role": "alice", "content": "I like trail running."}], session_id="new", date="2026-07-29"
    )

    assert created[0].id == "newF1"
    assert created[0].sources[0]["content"] == "I like trail running."
    assert created[0].metadata["objects"] == ("activity",)
    assert extraction_modes == [True]
    assert "newF1" in path.read_text(encoding="utf-8")


def test_remember_rejects_invalid_messages(tmp_path):
    path = tmp_path / "memory.xml"
    path.write_bytes(DEMO.read_bytes())
    memory = Memory.load(path, model="test:model")
    with pytest.raises(KiteError, match="messages"):
        memory.remember("not messages")
    with pytest.raises(KiteError, match="non-empty"):
        memory.remember([{"role": "alice", "content": ""}])
    with pytest.raises(KiteError, match="include_facets"):
        memory.remember([("alice", "Hello")], include_facets="yes")
    with pytest.raises(KiteError, match="valid ISO date"):
        memory.remember([("alice", "Hello")], date="2026-02-31")
    before = path.read_bytes()
    with pytest.raises(KiteError, match="XML control"):
        memory.remember([("ali\x01ce", "Hello")])
    assert path.read_bytes() == before


def test_remember_never_replaces_memory_with_malformed_provider_xml(tmp_path, monkeypatch):
    path = tmp_path / "memory.xml"
    path.write_bytes(DEMO.read_bytes())
    before = path.read_bytes()
    memory = Memory.load(path, model="test:model")
    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)
    monkeypatch.setattr(
        "memoket_kite.memory.extract_facts",
        lambda *args, **kwargs: [
            {
                "content": "A valid-looking fact.",
                "kind": "event",
                "who": "ali\x01ce",
                "t": "2026-08-11",
                "conf": "high",
                "topics": [],
                "entities": [],
                "src": ["unsafeL1"],
            }
        ],
    )

    with pytest.raises(KiteError, match="could not update memory file"):
        memory.remember([("alice", "Hello")], session_id="unsafe", date="2026-08-11")

    assert path.read_bytes() == before


def test_memory_requires_a_configured_provider(monkeypatch):
    memory = Memory.load(DEMO, model="test:model")
    monkeypatch.setattr(
        "memoket_kite.memory.ensure_configured",
        lambda model: (_ for _ in ()).throw(RuntimeError("No LLM provider is configured.")),
    )

    with pytest.raises(KiteError, match="No LLM provider"):
        memory.recall("What does Alice like?")
    with pytest.raises(KiteError, match="No LLM provider"):
        memory.answer("What does Alice like?")
    with pytest.raises(KiteError, match="No LLM provider"):
        memory.remember([("alice", "I like trail running.")])


def test_basic_recall_example_prints_facts_and_sources(monkeypatch, capsys):
    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)
    monkeypatch.setattr("memoket_kite.memory.fact_from_stored", lambda fact: fact)
    monkeypatch.setattr(
        "memoket_kite.memory.Memory._reasoner",
        lambda self: SimpleNamespace(
            retrieve=lambda *args, **kwargs: SimpleNamespace(
                evidence=(SimpleNamespace(type="fact", **_fact().__dict__),)
            )
        ),
    )
    path = Path(__file__).parents[2] / "examples" / "basic_recall.py"
    spec = importlib.util.spec_from_file_location("basic_recall_example", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    module.main()

    output = capsys.readouterr().out
    assert "Alice likes trail running." in output
    assert "source: I like running." in output


def test_remember_takes_only_parameters_it_persists(tmp_path, monkeypatch):
    """A parameter the API cannot honour is a parameter it does not take.

    `title` is written into the session element and can be read back, so it is
    accepted. A general metadata mapping has nowhere to go in the file, so
    passing one is a TypeError rather than a silent discard.
    """
    path = tmp_path / "memory.xml"
    path.write_bytes(DEMO.read_bytes())
    memory = Memory.load(path, model="test:model")
    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)
    monkeypatch.setattr(
        "memoket_kite.memory.extract_facts", lambda vocab, session, model, include_facets: []
    )

    memory.remember([("alice", "Hello.")], session_id="titled", title="Standup")
    assert 'title="Standup"' in path.read_text(encoding="utf-8")

    with pytest.raises(TypeError):
        memory.remember([("alice", "Hi.")], session_id="x", metadata={"project": "apollo"})


def test_a_failed_write_does_not_leave_phantom_topics_in_memory(tmp_path, monkeypatch):
    """Extraction proposes topics as it reads; a failed write must discard them.

    Proposals have to land in a copy of the vocabulary until the file is
    written: mutate the live one first and a failed write leaves proposals in
    memory that the next successful remember() persists as if they had been
    accepted.
    """
    path = tmp_path / "memory.xml"
    path.write_bytes(DEMO.read_bytes())
    memory = Memory.load(path, model="test:model")
    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)

    def poisoning_extract(vocab, session, model, include_facets):
        vocab.topics["phantom_topic"] = vocab.topics[next(iter(vocab.topics))]
        raise RuntimeError("provider died mid-extraction")

    monkeypatch.setattr("memoket_kite.memory.extract_facts", poisoning_extract)
    with pytest.raises(KiteError):
        memory.remember([("alice", "Hello.")], session_id="doomed")
    assert "phantom_topic" not in memory._book._vocab.topics

    # ...and a duplicate session id is refused before extraction is paid for
    calls = []
    monkeypatch.setattr(
        "memoket_kite.memory.extract_facts",
        lambda *a, **k: calls.append(1) or [],
    )
    with pytest.raises(KiteError, match="already exists"):
        memory.remember([("alice", "Hello.")], session_id="s1")
    assert calls == []


def test_default_profile_answers_carry_citations_and_policies(monkeypatch):
    """The shipped default profile must round-trip citations for real.

    The prompt names the JSON key it wants for citations and the pipeline reads
    one key back; if the two disagree, every public answer carries empty
    citations and nothing else fails. A test that stubs the answer record after
    the parse cannot see that, so this one drives the real compile -> retrieve
    -> answer path and replies in EXACTLY the shape the prompt asks for, which
    makes the two sides fail together. It also pins that KERNEL_POLICIES
    reaches the reader: a template without a {policies} placeholder formats
    cleanly and drops them.
    """
    import re

    from memoket_kite.pipeline import answer as answer_module
    from memoket_kite.pipeline import compile_plan as compile_module

    memory = Memory.load(DEMO, model="test:model")
    monkeypatch.setattr("memoket_kite.memory.ensure_configured", lambda model: None)

    monkeypatch.setattr(
        compile_module,
        "llm_json",
        lambda prompt, **kwargs: {
            "queries": [
                {"select": "facts", "where": {"topics": [{"code": "activities", "closure": True}]}}
            ],
            "intent": "factual",
        },
    )

    seen_prompts = []

    def scripted_reader(prompt, **kwargs):
        seen_prompts.append(prompt)
        # Reply in the exact shape THIS prompt requests, citing a source id
        # lifted from the evidence it was shown.
        requested = re.search(r'"answer":str,"(\w+)"', prompt)
        cited = re.search(r"\((s\d+[FL]\d+)", prompt)
        assert requested and cited, "prompt lost its schema line or its evidence rows"
        # A fabricated id rides along: validation must drop it and keep the
        # real one, or the public API publishes receipts for nothing.
        return {
            "answer": "The Shanghai Marathon.",
            requested.group(1): [cited.group(1), "not-in-pack", cited.group(1)],
        }

    monkeypatch.setattr(answer_module, "llm_json", scripted_reader)

    result = memory.answer_with_evidence("What race is Alice training for?")
    assert result.text == "The Shanghai Marathon."
    assert result.citations, "a cited answer under the default profile lost its citations"
    assert "not-in-pack" not in result.citations, "a fabricated citation id was published"
    assert len(result.citations) == len(set(result.citations)), "citations must be deduplicated"
    first_prompt = seen_prompts[0]
    assert "POLICIES:" in first_prompt, "KERNEL_POLICIES never reached the reader"
    assert "No information" in first_prompt, "the refusal contract fell out of the policies"


def test_a_provider_outage_surfaces_as_provider_error_through_both_apis(tmp_path):
    """The research API wraps everything in its own hierarchy (ReasoningError),
    and the Memory boundary must translate the cause chain back to the public
    ProviderError — re-labelled, a provider outage is uncatchable by contract."""
    import shutil
    from unittest.mock import patch

    import pytest

    import memoket_kite.memory as memory_module
    from memoket_kite import Memory, ProviderError
    from memoket_kite.errors import KiteError
    from memoket_kite.research.codebook import Codebook, Reasoner
    from memoket_kite.research.errors import ReasoningError, ResearchError

    source = Path(__file__).resolve().parents[2] / "examples/data/demo_codebook.xml"
    path = tmp_path / "cb.xml"
    shutil.copy(source, path)
    outage = ProviderError("llm failed: connection refused")

    with patch("memoket_kite.pipeline.answer.answer", side_effect=outage):
        # Research API: stays inside its own hierarchy, cause preserved.
        from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE

        reasoner = Reasoner(Codebook.load(path), profile=DEFAULT_MEMORY_PROFILE, model="m")
        with pytest.raises(ReasoningError) as info:
            reasoner.answer("where?")
        assert isinstance(info.value, ResearchError)
        assert info.value.__cause__ is outage

        # Memory API: the documented ProviderError, not a generic KiteError.
        with patch.object(memory_module, "ensure_configured", lambda *a, **k: None):
            memory = Memory.load(str(path))
            with pytest.raises(ProviderError):
                memory.answer("where?")
            with pytest.raises(KiteError):  # ProviderError is still a KiteError
                memory.answer("where?")


def test_the_readme_quickstart_file_can_grow_a_taxonomy(tmp_path):
    """A new topic must attach to an existing parent, so the quickstart file
    ships seed roots: under an empty <vocab/> every proposal is an orphan and
    is rejected, and the taxonomy can never begin to grow."""
    from unittest.mock import patch

    import memoket_kite.memory as memory_module
    import memoket_kite.pipeline.extract as extract_module
    from memoket_kite import Memory

    # Byte-for-byte the file the README's step 1 writes.
    path = tmp_path / "quickstart.xml"
    path.write_text(
        """<codebook id="quickstart">
  <vocab>
    <topic code="activities" status="canonical" parents="" born="" />
    <topic code="people" status="canonical" parents="" born="" />
    <topic code="places" status="canonical" parents="" born="" />
    <topic code="work" status="canonical" parents="" born="" />
    <topic code="preferences" status="canonical" parents="" born="" />
  </vocab>
  <timeline />
</codebook>
""",
        encoding="utf-8",
    )
    payload = {
        "proposals": [{"code": "running", "parent": "activities"}],
        "facts": [
            {
                "t": "2026-08-01",
                "kind": "event",
                "text": "The user started running.",
                "src": ["s1:0"],
                "topics": ["running"],
            }
        ],
    }
    with (
        patch.object(extract_module, "llm_json", return_value=payload),
        patch.object(memory_module, "ensure_configured", lambda *a, **k: None),
    ):
        Memory.load(str(path)).remember(
            [{"role": "user", "content": "I started running."}], session_id="s1"
        )
    text = path.read_text(encoding="utf-8")
    assert 'code="running"' in text  # admitted under the seed root, not orphaned
    Memory.load(str(path))


def test_a_session_that_cannot_be_read_back_never_replaces_the_memory(tmp_path):
    """The write path publishes only what the reader will accept.

    Parsing the temporary file proves it is XML, not that it is a memory. A
    symbol the writer allows but the loader refuses produces a syntactically
    valid file that can never be opened again, and it lands on top of the
    user's only durable copy. The guard loads the artifact the way a reader
    will, before the replace.
    """
    import shutil
    from unittest.mock import patch

    from memoket_kite import storage
    from memoket_kite.errors import StorageError

    source = Path(__file__).resolve().parents[2] / "examples/data/demo_codebook.xml"
    path = tmp_path / "cb.xml"
    shutil.copy(source, path)
    before = path.read_bytes()

    session = {
        "id": "sQ",
        "date": "2026-01-01",
        "weekday": "Thursday",
        "time": "09:00",
        "t": "2026-01-01T09:00",
        "bucket": "2026-01",
        "title": "",
        "dur": "",
        "n_lines": 1,
        "speakers": ["user"],
        "utterances": [("sQ:0", "user", "", "hello")],
    }
    with (
        patch.object(storage, "_verify_loadable", side_effect=StorageError("unreadable")),
        pytest.raises(StorageError),
    ):
        storage.append_session(path, session, [], Vocab())
    assert path.read_bytes() == before
