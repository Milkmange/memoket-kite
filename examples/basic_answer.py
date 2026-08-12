"""Start here: ask an evidence-backed question about a memory artifact.

Configure an LLM provider first (see .env.example), then run:
    python examples/basic_answer.py
"""

from pathlib import Path

from memoket_kite import Memory


def main() -> None:
    memory = Memory.load(Path(__file__).parent / "data" / "demo_codebook.xml")
    answer = memory.answer("What race is Alice preparing for?")
    print(answer)


if __name__ == "__main__":
    main()
