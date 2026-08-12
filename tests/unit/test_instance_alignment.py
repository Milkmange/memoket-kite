"""Offline checks for completed-Codebook finalization."""

import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from benchmarks.locomo import build as locomo_build
from benchmarks.locomo import profile as locomo_profile
from benchmarks.longmemeval import adapter as longmemeval_adapter
from benchmarks.longmemeval import build as longmemeval_build
from benchmarks.longmemeval import profile as longmemeval_profile
from memoket_kite.pipeline.extract import finalize_instance_alignment

DEMO = Path(__file__).parents[2] / "examples" / "data" / "demo_codebook.xml"


def test_longmemeval_declares_both_finalization_stages():
    assert longmemeval_profile.INSTANCE_ALIGNMENT is True
    assert longmemeval_profile.TOPIC_REFINEMENT is True
    assert getattr(locomo_profile, "INSTANCE_ALIGNMENT", False) is False
    assert getattr(locomo_profile, "TOPIC_REFINEMENT", False) is False


def test_instance_alignment_writes_a_registry_without_rewriting_facts(tmp_path, monkeypatch):
    codebook = tmp_path / "demo.xml"
    shutil.copy(DEMO, codebook)
    original_facts = [fact.get("id") for fact in ET.parse(codebook).iter("fact")]
    calls = []

    def no_alignment_call(*args, **kwargs):
        calls.append((args, kwargs))
        return {"clusters": []}

    monkeypatch.setattr("memoket_kite.pipeline.extract.llm_json", no_alignment_call)
    instances = finalize_instance_alignment(str(codebook), model="gpt-4.1-mini")

    root = ET.parse(codebook).getroot()
    assert instances == []
    assert root.find("instances") is not None
    assert [fact.get("id") for fact in root.iter("fact")] == original_facts
    assert len(calls) == 1
    assert "repeated Fact mentions" in calls[0][0][0]


def test_instance_alignment_cannot_corrupt_the_codebook_with_provider_xml(tmp_path, monkeypatch):
    codebook = tmp_path / "demo.xml"
    shutil.copy(DEMO, codebook)
    original = codebook.read_bytes()
    monkeypatch.setattr(
        "memoket_kite.pipeline.extract.llm_json",
        lambda *args, **kwargs: {
            "clusters": [
                {
                    "instances": [
                        {
                            "ids": ["s1F1", "s2F1"],
                            "label": "bad\x01label",
                            "kind": "event",
                        }
                    ]
                }
            ]
        },
    )

    with pytest.raises(ET.ParseError):
        finalize_instance_alignment(str(codebook), model="test:model")

    assert codebook.read_bytes() == original
    ET.parse(codebook)
    assert not list(tmp_path.glob(".instances-*.xml"))


def test_longmemeval_finalization_order_and_atomic_publication(tmp_path, monkeypatch):
    order = []
    monkeypatch.setattr(longmemeval_build, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(longmemeval_adapter, "iter_units", lambda instance: ())

    def align(path, **kwargs):
        order.append("instances")
        tree = ET.parse(path)
        ET.SubElement(tree.getroot(), "instances")
        tree.write(path, encoding="unicode", xml_declaration=True)
        return []

    def refine(root, **kwargs):
        order.append("topics")
        return 0

    monkeypatch.setattr(longmemeval_build, "finalize_instance_alignment", align)
    monkeypatch.setattr(longmemeval_build, "refine_topic_assignments", refine)

    result = longmemeval_build.build_codebook({"question_id": "q1"}, model="gpt-4.1-mini")

    assert result == "q1: built"
    assert order == ["instances", "topics"]
    assert (tmp_path / "q1.xml").exists()
    assert not list(tmp_path.glob(".q1.*.xml"))


def test_locomo_build_refuses_malformed_provider_xml_before_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(locomo_build, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(
        locomo_build.adapter,
        "iter_units",
        lambda sample: (
            {
                "id": "sample-S1",
                "date": "2026-08-11",
                "speakers": ("alice",),
                "utterances": (("L1", "alice", "", "hello"),),
            },
        ),
    )
    monkeypatch.setattr(
        locomo_build,
        "extract_facts",
        lambda *args, **kwargs: [
            {
                "content": "fact",
                "kind": "event",
                "who": "bad\x01speaker",
                "t": "2026-08-11",
                "conf": "high",
                "topics": [],
                "entities": [],
                "src": ["L1"],
            }
        ],
    )
    sample = {"sample_id": "sample", "conversation": {"speaker_a": "alice"}}

    with pytest.raises(ET.ParseError):
        locomo_build.build_sample(sample, model="test:model")

    assert not (tmp_path / "sample.xml").exists()


def test_longmemeval_revalidates_xml_after_topic_refinement(tmp_path, monkeypatch):
    monkeypatch.setattr(longmemeval_build, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(longmemeval_adapter, "iter_units", lambda instance: ())
    monkeypatch.setattr(longmemeval_build, "finalize_instance_alignment", lambda *a, **k: [])

    def corrupt_topic(root, **kwargs):
        root.find(".//topic").set("code", "bad\x01topic")
        return 1

    monkeypatch.setattr(longmemeval_build, "refine_topic_assignments", corrupt_topic)

    with pytest.raises(ET.ParseError):
        longmemeval_build.build_codebook({"question_id": "q1"}, model="test:model")

    assert not (tmp_path / "q1.xml").exists()


def test_topic_refinement_cache_binds_rendered_facts_and_taxonomy(tmp_path, monkeypatch):
    root = ET.fromstring(
        """
        <codebook>
          <vocab>
            <topic code="root" />
            <topic code="child" parents="root" />
          </vocab>
          <timeline>
            <session id="s1"><fact id="f1" topics="root">alpha fact</fact></session>
          </timeline>
        </codebook>
        """
    )
    calls = []

    def refine(prompt, model):
        calls.append((prompt, model))
        return {"assignments": []}

    monkeypatch.setattr(longmemeval_build, "llm_json", refine)

    longmemeval_build.refine_topic_assignments(root, model="test:model", cache_dir=tmp_path)
    longmemeval_build.refine_topic_assignments(root, model="test:model", cache_dir=tmp_path)
    assert len(calls) == 1, "identical refinement input must hit its cache"

    root.find(".//fact").text = "beta fact"
    longmemeval_build.refine_topic_assignments(root, model="test:model", cache_dir=tmp_path)
    assert len(calls) == 2, "changed facts must miss the refinement cache"

    ET.SubElement(root.find(".//vocab"), "topic", code="new", parents="root")
    longmemeval_build.refine_topic_assignments(root, model="test:model", cache_dir=tmp_path)
    assert len(calls) == 3, "changed taxonomy must miss the refinement cache"


def test_topic_refinement_cache_recovers_from_a_partial_entry(tmp_path, monkeypatch):
    root = ET.fromstring(
        """
        <codebook>
          <vocab><topic code="root" /></vocab>
          <timeline>
            <session id="s1"><fact id="f1" topics="root">alpha fact</fact></session>
          </timeline>
        </codebook>
        """
    )
    calls = []

    def refine(prompt, model):
        calls.append((prompt, model))
        return {"assignments": []}

    monkeypatch.setattr(longmemeval_build, "llm_json", refine)
    longmemeval_build.refine_topic_assignments(root, model="test:model", cache_dir=tmp_path)
    cache_path = next(tmp_path.glob("s1.*.json"))
    cache_path.write_text("{", encoding="utf-8")

    longmemeval_build.refine_topic_assignments(root, model="test:model", cache_dir=tmp_path)

    assert len(calls) == 2
    assert cache_path.read_text(encoding="utf-8").endswith("}")
    assert not list(tmp_path.glob(".refine-*.tmp"))


def test_topic_refinement_rejects_unknown_symbolic_labels(tmp_path, monkeypatch):
    root = ET.fromstring(
        """
        <codebook>
          <vocab>
            <topic code="root" />
            <topic code="child" parents="root" />
          </vocab>
          <timeline>
            <session id="s1"><fact id="f1" topics="child">alpha fact</fact></session>
          </timeline>
        </codebook>
        """
    )
    monkeypatch.setattr(
        longmemeval_build,
        "llm_json",
        lambda *args, **kwargs: {
            "new_codes": [{"code": "Bad Topic!", "parent": "missing_parent"}],
            "assignments": [{"id": "f1", "topics": ["phantom_topic"]}],
        },
    )

    changed = longmemeval_build.refine_topic_assignments(
        root, model="test:model", cache_dir=tmp_path
    )

    assert changed == 0
    assert root.find(".//fact").get("topics") == "child"
    assert {topic.get("code") for topic in root.iter("topic")} == {"root", "child"}
