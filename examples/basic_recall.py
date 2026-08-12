"""Start here: recall structured facts from a KITE memory artifact.

Configure an LLM provider first (see .env.example), then run:
    python examples/basic_recall.py
"""

from pathlib import Path

from memoket_kite import Memory


def main() -> None:
    memory = Memory.load(Path(__file__).parent / "data" / "demo_codebook.xml")
    facts = memory.recall("What race is Alice preparing for?")

    for fact in facts:
        print(fact.content)
        for source in fact.sources:
            print(f"  source: {source['content']}")


if __name__ == "__main__":
    main()
