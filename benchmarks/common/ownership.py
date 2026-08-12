"""Which result files a run directory is allowed to contain.

The LoCoMo scorer discovers results by globbing the directory, so any stray
`results_*.jsonl` — a manual copy, a file from a differently scoped run, or one
being written by a concurrent process — silently joins the denominator. The
manifest already declares which samples the run owns; checking the glob against
that declaration makes it binding for the evaluator and the scorer alike.
"""

from __future__ import annotations

import json
from pathlib import Path


def declared_samples(result_dir: Path) -> list | None:
    """The sample indices the manifest claims, or None when there is no manifest."""
    path = result_dir / "manifest.json"
    if not path.exists():
        return None
    return json.loads(path.read_text()).get("samples")


def owned_paths(result_dir: Path, sample_ids: list[str]) -> list[Path]:
    """Where the results for `sample_ids` belong, whether or not they exist yet.

    The naming rule lives here alone, so the writer and the ownership check
    cannot disagree about which filename a sample maps to.
    """
    return [result_dir / f"results_{sample_id}.jsonl" for sample_id in sample_ids]


def check(result_dir: Path, sample_ids: list[str]) -> list[Path]:
    """The owned result files, refusing any the manifest does not account for.

    Returns only the files that exist: a run in progress owns paths it has not
    written yet, and their absence is not a violation. An extra file is, since
    the glob the scorer uses would pick it up.
    """
    owned = owned_paths(result_dir, sample_ids)
    expected = {path.name for path in owned}
    present = {path.name for path in result_dir.glob("results_*.jsonl")}
    if foreign := sorted(present - expected):
        raise SystemExit(
            f"{result_dir.name} holds result files its manifest does not declare: "
            f"{', '.join(foreign)}. They would silently join the score. "
            f"Move them aside or use a new --tag."
        )
    return [path for path in owned if path.exists()]
