"""Reading back a partially written results file.

A long run killed mid-write leaves the final line truncated. Failing the whole
resume on it throws away hours of paid work; merely *skipping* it in memory is
worse than failing — the evaluator then appends onto the broken line, so the
next completed question is written inside it and lost for good.

So the truncated tail is removed from the file, not from the return value.

Recovery works on bytes, not text. Both harnesses write with
`ensure_ascii=False`, so a kill can land between the bytes of one character;
decoding the whole file first would raise before any of this logic ran. The
repair is written to a sibling temporary file and moved into place, so a second
crash cannot leave the results shorter than the evidence kept beside them.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def _backup(path: Path) -> Path:
    """A recovery copy that never overwrites evidence from an earlier repair.

    `touch(exist_ok=False)` claims the name in the same operation that tests
    it, so the copy cannot land on a file another repair is already using.
    """
    for suffix in range(100):
        candidate = path.with_suffix(
            path.suffix + (".partial" if not suffix else f".partial{suffix}")
        )
        try:
            candidate.touch(exist_ok=False)
            return candidate
        except FileExistsError:
            continue
    raise RuntimeError(f"too many recovery copies beside {path}")


def _complete_lines(raw: bytes, path: Path) -> list[bytes]:
    """The prefix of physical lines that decode and parse; only the last may fail.

    A line without a terminating newline is the one a kill can truncate. Any
    earlier damage, or a fully-written line that is not valid JSON, is real
    corruption and must not be silently discarded.
    """
    lines = raw.split(b"\n")
    unterminated = bool(lines and lines[-1])
    if not unterminated:
        lines.pop()  # trailing newline produces an empty final element
    complete: list[bytes] = []
    for index, line in enumerate(lines):
        if not line.strip():
            continue
        last = index == len(lines) - 1
        try:
            json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            if not (last and unterminated):
                raise RuntimeError(
                    f"{path} is corrupt at line {index + 1} of {len(lines)}; "
                    f"only a truncated final line can be recovered"
                ) from None
            break
        complete.append(line)
    return complete


def completed_rows(path: Path) -> list[dict]:
    """Every complete record in `path`, truncating a partially written tail.

    The file is left in a state the evaluator can safely append to: every line
    is a whole record and the last one ends with a newline.
    """
    if not path.exists():
        return []
    raw = path.read_bytes()
    complete = _complete_lines(raw, path)
    repaired = b"".join(line + b"\n" for line in complete)
    if repaired != raw:
        evidence = _backup(path)
        evidence.write_bytes(raw)
        temporary = path.with_suffix(path.suffix + ".repair")
        with temporary.open("wb") as stream:
            stream.write(repaired)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)  # atomic: the file is never half-repaired
        dropped = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0) - len(complete)
        print(
            f"  recovered {path.name}: kept {len(complete)} complete records, "
            f"dropped {max(dropped, 0)} truncated line(s); original saved as {evidence.name}"
        )
    return [json.loads(line.decode("utf-8")) for line in complete]
