"""Audit benchmark prompts for terms concentrated in a small part of a corpus.

This is a diagnostic gate, not an automatic verdict. A concentrated prompt
term may be task language or may accidentally reveal dataset content; every
finding requires review.
"""

from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

from benchmarks.common.paths import DATASETS_ROOT

GENERIC_TERMS = set(
    """about after all answer any are code codes content conversation date dates
    duration entities entity event events evidence extract fact facts field
    fields filter filters first format from group id ids index json kind kinds
    list memory model name names plan plans prompt question questions record
    result return root rules schema search session sessions source sources
    speaker speakers specific stage subject taxonomy text time topic topics
    unit units value values where who with year years""".split()
)

CORPORA = {
    "locomo": DATASETS_ROOT / "locomo" / "locomo10.json",
    "longmemeval": DATASETS_ROOT / "longmemeval" / "longmemeval_s_cleaned.json",
}


def _prompt_terms(text: str) -> set[str]:
    terms = set()
    for word in re.findall(r"[a-z][a-z_]{3,}", text.lower()):
        terms.update(
            part for part in word.split("_") if len(part) > 3 and part not in GENERIC_TERMS
        )
    return terms


def _documents(path: Path) -> list[str]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.dumps(item).lower() for item in json.load(stream)]


def audit() -> list[tuple]:
    corpora = {name: _documents(path) for name, path in CORPORA.items()}
    findings = []
    for benchmark in CORPORA:
        profile = importlib.import_module(f"benchmarks.{benchmark}.profile")
        for attribute in dir(profile):
            if not attribute.endswith("_PROMPT"):
                continue
            prompt = getattr(profile, attribute)
            if not isinstance(prompt, str):
                continue
            for term in sorted(_prompt_terms(prompt)):
                pattern = re.compile(r"\b" + re.escape(term))
                for corpus, documents in corpora.items():
                    if not documents:
                        continue
                    matching = [document for document in documents if pattern.search(document)]
                    count = sum(document.count(term) for document in matching)
                    if matching and len(matching) / len(documents) <= 0.30 and count >= 5:
                        findings.append(
                            (
                                benchmark,
                                attribute,
                                term,
                                corpus,
                                len(matching),
                                len(documents),
                                count,
                            )
                        )
    return findings


def main() -> int:
    findings = audit()
    if not findings:
        print("No concentrated prompt terms found.")
        return 0
    print("Prompt terms requiring manual review:")
    for item in sorted(findings, key=lambda value: (value[4] / value[5], -value[6])):
        print(
            f"{item[0]}.{item[1]} term={item[2]!r} corpus={item[3]} "
            f"documents={item[4]}/{item[5]} occurrences={item[6]}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
