"""Tests for single-pass Fact extraction with optional retrieval facets."""

from memoket_kite.core.vocab import Vocab
from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE
from memoket_kite.pipeline import extract as extraction


def _session() -> dict:
    return {
        "id": "s1",
        "date": "2026-07-30",
        "speakers": ("alice",),
        "utterances": [
            ("s1L1", "alice", "", "I moved to New York with two dogs for two weeks."),
        ],
    }


def _model_response() -> dict:
    return {
        "facts": [
            {
                "content": "Alice moved to New York with two dogs for two weeks.",
                "kind": "event",
                "who": "alice",
                "t": "2026-07-30",
                "conf": "high",
                "topics": ["personal_life"],
                "entities": ["New York"],
                "src": ["s1L1"],
                "facets": {
                    "object": ["dogs"],
                    "place": ["New York"],
                    "event": ["move"],
                    "duration": "P2W",
                },
            }
        ],
        "proposals": [],
        "entity_types": {"New York": "place"},
    }


def _vocabulary() -> Vocab:
    vocabulary = Vocab()
    vocabulary.define_root("personal_life")
    return vocabulary


def test_default_extraction_returns_facets_in_one_model_call(monkeypatch):
    prompts = []

    def fake_llm_json(prompt, model):
        prompts.append(prompt)
        return _model_response()

    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)
    facts = extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
    )

    assert len(prompts) == 1
    assert '"facets"' in prompts[0]
    assert facts[0]["obj"] == ["dog"]
    assert facts[0]["place"] == ["new_york"]
    assert facts[0]["event"] == ["move"]
    assert facts[0]["dur"] == "P2W"


def test_facet_free_extraction_uses_ablation_prompt_and_drops_facets(monkeypatch):
    prompts = []

    def fake_llm_json(prompt, model):
        prompts.append(prompt)
        return _model_response()

    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)
    facts = extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        include_facets=False,
    )

    assert len(prompts) == 1
    assert '"facets"' not in prompts[0]
    assert not {"obj", "place", "event", "dur"} & facts[0].keys()


def test_extraction_rejects_provider_kind_and_date_schema_drift(monkeypatch):
    response = _model_response()
    response["facts"][0]["kind"] = "made up class"
    response["facts"][0]["t"] = "tomorrow"
    monkeypatch.setattr(extraction, "llm_json", lambda prompt, model: response)

    facts = extraction.extract_facts(
        _vocabulary(), DEFAULT_MEMORY_PROFILE, _session(), model="test:model"
    )

    assert facts[0]["kind"] == "other"
    assert facts[0]["t"] == ""


def test_extraction_accepts_only_real_month_or_day_precision_dates(monkeypatch):
    response = _model_response()
    dates = iter(("2026-02", "2026-02-31", "2026-13", "2026-02-03T10:00"))

    def reply(prompt, model):
        response["facts"][0]["t"] = next(dates)
        return response

    monkeypatch.setattr(extraction, "llm_json", reply)
    actual = [
        extraction.extract_facts(
            _vocabulary(), DEFAULT_MEMORY_PROFILE, _session(), model="test:model"
        )[0]["t"]
        for _ in range(4)
    ]

    assert actual == ["2026-02", "", "", ""]


def test_extraction_never_iterates_scalar_provider_arrays(monkeypatch):
    response = _model_response()
    first = response["facts"][0]
    first["topics"] = "personal_life"
    first["entities"] = "Alice"
    second = dict(first, content="scalar source", topics=[], entities=[], src="s1L1")
    response["facts"] = [first, second]
    monkeypatch.setattr(extraction, "llm_json", lambda prompt, model: response)
    vocabulary = _vocabulary()

    facts = extraction.extract_facts(
        vocabulary, DEFAULT_MEMORY_PROFILE, _session(), model="test:model"
    )

    assert len(facts) == 1, "a scalar source id must not be treated as a character array"
    assert facts[0]["topics"] == []
    assert facts[0]["entities"] == []
    assert not {"a", "l", "i", "c", "e"} & set(vocabulary.entities)


def test_extraction_discards_non_string_provider_fields(monkeypatch):
    response = _model_response()
    first = response["facts"][0]
    first.update(
        {
            "who": ["Alice"],
            "topics": ["personal_life", 123, {"code": "invented"}],
            "entities": ["Alice", 123, True, {"name": "Invented"}],
            "facets": {"object": [123, {"name": "Invented"}, "dogs"]},
        }
    )
    response["facts"].append(dict(first, content=123, who="alice"))
    response["entity_types"] = {"Alice": "person", 123: "number", "Bad": ["type"]}
    monkeypatch.setattr(extraction, "llm_json", lambda prompt, model: response)
    vocabulary = _vocabulary()

    facts = extraction.extract_facts(
        vocabulary, DEFAULT_MEMORY_PROFILE, _session(), model="test:model"
    )

    assert len(facts) == 1, "a non-string content value must not become durable text"
    assert facts[0]["who"] == ""
    assert facts[0]["topics"] == ["personal_life"]
    assert facts[0]["entities"] == ["alice"]
    assert facts[0]["obj"] == ["dog"]
    assert set(vocabulary.entities) == {"alice"}


def test_duplicate_decisions_cannot_forge_a_topic_consolidation_majority(monkeypatch):
    vocabulary = Vocab()
    vocabulary.define_root("root")
    for unit in ("u1", "u2"):
        vocabulary.propose_topic("alpha", "root", unit=unit)
        vocabulary.propose_topic("beta", "root", unit=unit)
    responses = iter(
        [
            {
                "decisions": [
                    {"i": 0, "merge": True, "winner": "alpha"},
                    {"i": 0, "merge": True, "winner": "alpha"},
                ]
            },
            {"decisions": []},
            {"decisions": []},
        ]
    )
    monkeypatch.setattr(extraction, "llm_json", lambda *args, **kwargs: next(responses))

    rewrites = extraction.consolidate_topics(vocabulary, [], model="test:model")

    assert rewrites == {}
    assert {"alpha", "beta"} <= vocabulary.topics.keys()


def test_duplicate_decisions_cannot_forge_an_entity_consolidation_majority(monkeypatch):
    vocabulary = Vocab()
    vocabulary.register_entity("alice")
    vocabulary.register_entity("alica")
    responses = iter(
        [
            {
                "decisions": [
                    {"i": 0, "merge": True, "winner": "alice"},
                    {"i": 0, "merge": True, "winner": "alice"},
                ]
            },
            {"decisions": []},
            {"decisions": []},
        ]
    )
    monkeypatch.setattr(extraction, "llm_json", lambda *args, **kwargs: next(responses))

    rewrites = extraction.consolidate_entities(vocabulary, [], model="test:model")

    assert rewrites == {}
    assert {"alice", "alica"} <= vocabulary.entities.keys()


def test_facet_and_ablation_caches_are_isolated(tmp_path, monkeypatch):
    calls = []

    def fake_llm_json(prompt, model):
        calls.append(prompt)
        return _model_response()

    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=False,
    )

    assert len(calls) == 2
    # The filename carries a fingerprint of (prompt template, model, provider),
    # so a cache built under one prompt can never answer for another.
    assert len(list(tmp_path.glob("s1.facets.*.json"))) == 1
    assert len(list(tmp_path.glob("s1.no-facets.*.json"))) == 1


def test_extraction_cache_reuses_an_identical_rendered_request(tmp_path, monkeypatch):
    calls = []

    def fake_llm_json(prompt, model):
        calls.append((prompt, model))
        return _model_response()

    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)
    for _ in range(2):
        extraction.extract_facts(
            _vocabulary(),
            DEFAULT_MEMORY_PROFILE,
            _session(),
            model="test:model",
            cache_dir=str(tmp_path),
            include_facets=True,
        )

    assert len(calls) == 1, "an identical rendered request must hit the extraction cache"


def test_extraction_cache_recovers_from_a_partial_entry(tmp_path, monkeypatch):
    calls = []

    def fake_llm_json(prompt, model):
        calls.append((prompt, model))
        return _model_response()

    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )
    cache_path = next(tmp_path.glob("s1.facets.*.json"))
    cache_path.write_text("{", encoding="utf-8")

    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )

    assert len(calls) == 2
    assert cache_path.read_text(encoding="utf-8").endswith("}")
    assert not list(tmp_path.glob(".extract-*.tmp"))


def test_extraction_cache_treats_schema_corruption_as_a_miss(tmp_path, monkeypatch):
    calls = []

    def fake_llm_json(prompt, model):
        calls.append((prompt, model))
        return _model_response()

    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )
    cache_path = next(tmp_path.glob("s1.facets.*.json"))
    cache_path.write_text('{"facts": null, "proposals": [], "entity_types": {}}', encoding="utf-8")

    facts = extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )

    assert len(calls) == 2
    assert facts


def test_extraction_cache_never_answers_for_a_different_prompt(tmp_path, monkeypatch):
    """The cache key covers the prompt template, not just the session id.

    Keyed on the session id alone, a cache built under one prompt answers for
    every later prompt, and the run then records the new prompt's hash beside
    the old prompt's responses — a provenance error no downstream check can
    detect, because both artifacts are internally consistent.
    """
    calls = []

    def scripted(prompt, model="m", **kwargs):
        calls.append(prompt)
        return {"facts": [], "proposals": [], "entity_types": {}}

    monkeypatch.setattr(extraction, "llm_json", scripted)
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )

    class RewordedProfile(DEFAULT_MEMORY_PROFILE):
        EXTRACT_PROMPT = DEFAULT_MEMORY_PROFILE.EXTRACT_PROMPT + "\nOne more rule."

    extraction.extract_facts(
        _vocabulary(),
        RewordedProfile,
        _session(),
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )
    assert len(calls) == 2, "a reworded prompt must miss the old cache"
    assert len(list(tmp_path.glob("s1.facets.*.json"))) == 2


def test_extraction_normalizes_sources_vocab_and_facets(monkeypatch):
    class FilteredProfile(DEFAULT_MEMORY_PROFILE):
        @staticmethod
        def entity_filter(name):
            return name != "Ignore Me"

    response = _model_response()
    response["proposals"] = [{"code": "trail_running", "parent": "personal_life"}]
    response["facts"][0].update(
        {
            "topics": ["trail_running", "unknown_topic"],
            "entities": ["New York", "Ignore Me"],
            "src": ["s1L1", "not-a-source"],
            "facets": {
                "object": ["dogs"],
                "place": ["New York"],
                "event": ["not_an_allowed_event"],
                "duration": "two weeks",
            },
        }
    )
    monkeypatch.setattr(extraction, "llm_json", lambda prompt, model: response)

    vocabulary = _vocabulary()
    facts = extraction.extract_facts(vocabulary, FilteredProfile, _session(), model="test:model")

    assert facts[0]["topics"] == ["trail_running"]
    assert facts[0]["entities"] == ["new_york"]
    assert facts[0]["src"] == ["s1L1"]
    assert facts[0]["obj"] == ["dog"]
    assert facts[0]["place"] == ["new_york"]
    assert "event" not in facts[0]
    assert "dur" not in facts[0]


def test_each_utterance_group_uses_one_extraction_request(monkeypatch):
    prompts = []

    def fake_llm_json(prompt, model):
        prompts.append(prompt)
        return _model_response()

    session = _session()
    session["utterance_groups"] = [session["utterances"], session["utterances"]]
    monkeypatch.setattr(extraction, "llm_json", fake_llm_json)

    extraction.extract_facts(_vocabulary(), DEFAULT_MEMORY_PROFILE, session, model="test:model")

    assert len(prompts) == 2


def test_extraction_cache_never_answers_for_different_content(tmp_path, monkeypatch):
    """The cache key covers the rendered request, not just the template.

    A session id is reused across corpora and a template fingerprint is blind
    to the dialog substituted into it, so a key built from those two alone lets
    one conversation's facts be served for another's.
    """
    calls = []

    def scripted(prompt, model="m", **kwargs):
        calls.append(prompt)
        return {"facts": [], "proposals": [], "entity_types": {}}

    monkeypatch.setattr(extraction, "llm_json", scripted)
    first = _session()
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        first,
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )
    changed = _session()
    changed["utterances"] = [
        (utterance_id, speaker, time_mark, "a completely different conversation")
        for utterance_id, speaker, time_mark, _content in changed["utterances"]
    ]
    changed.pop("utterance_groups", None)
    extraction.extract_facts(
        _vocabulary(),
        DEFAULT_MEMORY_PROFILE,
        changed,
        model="test:model",
        cache_dir=str(tmp_path),
        include_facets=True,
    )
    assert len(calls) == 2, "changed dialog under the same session id must miss the cache"
