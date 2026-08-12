"""Repository and artifact paths shared by benchmark modules.

Every artifact root hangs off `ARTIFACTS_ROOT`, so redirecting `KITE_ARTIFACTS_DIR`
moves datasets, codebooks, caches and results together and cannot leave one of
them pointing at the previous location. The override is expanded and resolved
once here, so every consumer joins onto the same absolute path regardless of the
working directory it runs from.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS_ROOT = (
    Path(os.environ.get("KITE_ARTIFACTS_DIR", REPO_ROOT / "artifacts")).expanduser().resolve()
)
DATASETS_ROOT = ARTIFACTS_ROOT / "datasets"
CODEBOOKS_ROOT = ARTIFACTS_ROOT / "codebooks"
CACHE_ROOT = ARTIFACTS_ROOT / "cache"
RESULTS_ROOT = ARTIFACTS_ROOT / "results"


def safe_tag(value: str) -> str:
    """Return a tag safe to embed as one artifact-directory component.

    A tag reaches the filesystem as `RESULTS_ROOT / tag`, so it must name a
    single child and nothing else: the pattern admits no separator and demands
    an alphanumeric first character, which also keeps a tag from reading as an
    option or hiding as a dotfile, and `..` is rejected wherever it appears.
    """
    tag = str(value or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", tag) or ".." in tag:
        raise ValueError("--tag must be a non-empty filename-safe identifier")
    return tag
