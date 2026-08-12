"""Publishing a result set as one transaction.

Writing the verdicts, then the manifest, then the score gives two ways to end
up with a directory that looks finished and is not: a crash between the
manifest and the score leaves a complete-looking manifest over a score that is
missing on a first publish or stale on a re-score, and the overwrite guard then
refuses the rerun that would repair it.

So nothing is published until everything is ready, each file is replaced
atomically, and the manifest — the thing that says "this artifact is complete"
— is written last.

Judging takes minutes, and the inputs are ordinary files. Whatever was true
when they were read has to still be true at the moment of sealing, or the
manifest binds digests to bytes that have since moved.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    """Replace `path` with `text`, or leave the old contents untouched.

    The bytes are flushed and fsynced into a sibling temporary file before
    `os.replace` swaps it in, so a reader of `path` sees either the previous
    contents or the complete new ones and never a partial write.
    """
    temporary = path.with_suffix(path.suffix + ".publishing")
    with temporary.open("w", encoding="utf-8") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def observe(paths) -> dict[str, str]:
    """Digest the inputs a scoring run depends on, keyed by path.

    A path that does not exist digests to the empty string rather than raising,
    so its later appearance registers as a change instead of stopping the
    observation. Keying by path rather than by a label is what lets `publish()`
    re-check an arbitrary set without a table of filenames to keep in sync.
    """
    return {
        str(path): hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""
        for path in paths
    }


def publish(
    result_dir: Path,
    *,
    judged: str,
    score: dict,
    manifest,
    observed: dict | None = None,
    guard=None,
    sealed: dict | None = None,
) -> dict:
    """Write the artifact, then seal it.

    `manifest` is called last, with a mapping from each path written to the
    bytes written there, so the seal describes this scorer's output rather
    than the file's current contents.

    `observed` is what `observe()` saw before judging began. Any of it that
    moved since means the seal would describe a state that never existed, so
    refuse before writing anything rather than after.

    `guard` re-checks anything a per-file digest cannot: a result file that
    *appeared* during judging changes the denominator without disturbing any
    digest already taken, because nothing was observing a path that did not
    exist yet.

    `sealed` carries bytes the caller read before judging began — the run
    manifest above all. Without it the seal digests whatever is on disk at
    seal time, so answers produced under one run identity could be sealed
    under another.
    """
    if observed:
        now = observe(Path(name) for name in observed)
        drifted = sorted(
            Path(name).name for name, digest in now.items() if digest != observed[name]
        )
        if drifted:
            raise SystemExit(
                f"{result_dir.name} changed while it was being judged "
                f"({', '.join(drifted)}); nothing was written. Re-score it."
            )
    if guard is not None:
        guard()
    judged_path = result_dir / "judged.jsonl"
    score_path = result_dir / "score.json"
    score_text = json.dumps(score, indent=2, sort_keys=True) + "\n"
    atomic_write(judged_path, judged)
    atomic_write(score_path, score_text)
    # The seal describes what THIS scorer wrote. Letting it re-read the files
    # would bind whatever a concurrent writer left there a millisecond later.
    return manifest(
        {
            **(sealed or {}),
            judged_path: judged.encode("utf-8"),
            score_path: score_text.encode("utf-8"),
        }
    )
