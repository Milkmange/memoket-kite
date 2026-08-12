"""Load and safely update XML memory artifacts."""

from __future__ import annotations

import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable

from memoket_kite.core.algebra import Store
from memoket_kite.defaults import DEFAULT_MEMORY_PROFILE
from memoket_kite.errors import StorageError
from memoket_kite.pipeline.extract import append_session_to_xml

PathInput = str | os.PathLike[str]


def _verify_loadable(path: Path) -> None:
    """Refuse to publish an artifact the loader would reject."""
    try:
        Store.load([str(path)])
    except (ET.ParseError, ValueError) as exc:
        raise StorageError(
            f"could not update memory file: the session was encoded into a memory that "
            f"cannot be read back ({exc}); the existing memory is unchanged"
        ) from exc


def source_paths(source: PathInput | Iterable[PathInput]) -> tuple[Path, ...]:
    values = (source,) if isinstance(source, (str, os.PathLike)) else tuple(source)
    if not values:
        raise StorageError("at least one XML memory file is required")
    paths = tuple(Path(value).expanduser() for value in values)
    for path in paths:
        if not path.exists() or not path.is_file():
            raise StorageError(f"memory file does not exist: {path}")
    return paths


def _symbol_codes(vocab_element) -> set[str]:
    return {
        f"{child.tag}:{child.get('code') or ''}"
        for child in vocab_element
        if child.tag in ("topic", "entity")
    }


def _refuse_stale_vocab(prior, incoming, path: Path) -> None:
    """Refuse a write whose vocabulary is older than the one on disk."""
    dropped = _symbol_codes(prior) - _symbol_codes(incoming)
    if dropped:
        raise StorageError(
            f"{path} changed since it was loaded: writing would drop "
            f"{len(dropped)} vocabulary symbol(s) another writer added "
            f"(e.g. {sorted(dropped)[:3]}); reload the memory and retry"
        )


def append_session(path: Path, session: dict, facts: list[dict], vocabulary) -> None:
    """Append one encoded session and atomically replace a single XML artifact."""
    try:
        tree = ET.parse(path)
        root = tree.getroot()
        timeline = root.find("timeline")
        if timeline is None:
            raise StorageError(f"memory file has no timeline: {path}")
        store, _ = Store.load([str(path)])
        if session["id"] in store.units:
            raise StorageError(f"session_id already exists: {session['id']}")
        append_session_to_xml(timeline, DEFAULT_MEMORY_PROFILE, session, facts)
        speakers = set((root.get("speakers") or "").split())
        speakers.update(session["speakers"])
        root.set("speakers", " ".join(sorted(speakers)))
        prior_vocab = root.find("vocab")
        new_vocab = vocabulary.to_xml()
        if prior_vocab is not None:
            # Fail closed on a stale writer. This instance's vocabulary was
            # loaded from an earlier revision of the file; writing it back
            # wholesale deletes symbols another writer added in between while
            # keeping the facts that reference them.
            _refuse_stale_vocab(prior_vocab, new_vocab, path)
        if prior_vocab is None:
            root.insert(0, new_vocab)
        else:
            root.insert(list(root).index(prior_vocab), new_vocab)
            root.remove(prior_vocab)
        ET.indent(tree, space="  ")
        with tempfile.NamedTemporaryFile(
            mode="wb", suffix=".xml", prefix=f".{path.stem}-", dir=path.parent, delete=False
        ) as handle:
            temporary = Path(handle.name)
            tree.write(handle, encoding="utf-8", xml_declaration=True)
        # Load the completed artifact the way a reader will, before it replaces
        # the user's only durable copy. Parsing alone accepts a file the loader
        # then refuses: a symbol the writer allowed but the reader rejects
        # produces valid XML that can never be opened again. Failing here costs
        # this remember() call; failing later costs the memory.
        _verify_loadable(temporary)
        # NamedTemporaryFile creates 0600; replacing in place would silently
        # tighten an existing file's permissions. Carry the original mode.
        try:
            os.chmod(temporary, os.stat(path).st_mode & 0o7777)
        except OSError:
            pass
        os.replace(temporary, path)
    except StorageError:
        raise
    except (OSError, ET.ParseError, TypeError, ValueError) as exc:
        raise StorageError(f"could not update memory file: {exc}") from exc
    finally:
        if "temporary" in locals() and temporary.exists():
            temporary.unlink(missing_ok=True)
