"""Inspect event time, source time, and query trace without an LLM."""

from pathlib import Path

from memoket_kite.research import Codebook, SymbolicQuery, TimeRange, TopicMatch

CODEBOOK = Path(__file__).parent / "data" / "demo_codebook.xml"


def main() -> None:
    book = Codebook.load(CODEBOOK)
    result = book.query(
        SymbolicQuery(
            topics=(TopicMatch("activities"),),
            time=TimeRange("2026-10-18", "2026-10-18"),
        )
    )
    fact = result.evidence[0]
    print(fact.text)
    print(f"source session date: {fact.source_time}")
    print(f"event date used by query: {fact.event_time}")
    print(f"trace stages: {len(result.trace.events)}")


if __name__ == "__main__":
    main()
