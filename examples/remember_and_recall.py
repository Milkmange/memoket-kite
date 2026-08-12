"""Add a conversation to a disposable XML memory, then recall it.

Configure an LLM provider first (see .env.example), then run:
    python examples/remember_and_recall.py

Pass --memory PATH to choose where the copied XML artifact is written.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from uuid import uuid4

from memoket_kite import Memory

FIXTURE = Path(__file__).parent / "data" / "demo_codebook.xml"
DEFAULT_MEMORY = Path("artifacts") / "quickstart_memory.xml"


def main() -> None:
    parser = argparse.ArgumentParser(description="Add and recall a KITE memory.")
    parser.add_argument("--memory", type=Path, default=DEFAULT_MEMORY)
    args = parser.parse_args()
    args.memory.parent.mkdir(parents=True, exist_ok=True)
    if not args.memory.exists():
        shutil.copyfile(FIXTURE, args.memory)
        print(f"Created working memory: {args.memory}")

    memory = Memory.load(args.memory)
    memory.remember(
        [{"role": "alice", "content": "I moved to Tokyo."}],
        session_id=f"quickstart-tokyo-{uuid4().hex[:8]}",
    )
    facts = memory.recall("Where did Alice move?")
    for fact in facts:
        print(fact.content)
        for source in fact.sources:
            print(f"  source: {source['content']}")


if __name__ == "__main__":
    main()
