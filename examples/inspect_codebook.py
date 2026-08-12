"""Inspect a KITE Codebook without an API key or network access."""

from pathlib import Path

from memoket_kite.research import Codebook, SymbolicQuery

CODEBOOK = Path(__file__).parent / "data" / "demo_codebook.xml"


def main() -> None:
    book = Codebook.load(CODEBOOK)
    inspector = book.inspect()
    summary = inspector.summary()
    print(f"units={summary.units} facts={summary.facts} lines={summary.lines}")
    print("\nControlled vocabulary:")
    print(inspector.topic_tree())
    print("\nStructured Facts and their source evidence:")
    result = book.query(SymbolicQuery(limit=summary.facts))
    for fact in sorted(result.evidence, key=lambda item: item.event_time or ""):
        print(f"- {fact.id} [{fact.event_time}] topics={','.join(fact.topics)}")
        print(f"  {fact.text}")
        print(f"  source: {' / '.join(source.text for source in fact.sources)}")


if __name__ == "__main__":
    main()
