"""Cache identity for benchmark judging.

A cached verdict is only reusable by the judge that produced it. A key built
from the question and the answer alone does not move when the rubric, the
protocol or the judge model changes, so an old label is served while the
summary prints the new judge's name: a corrupted score carrying correct-looking
provenance. Everything that can change a verdict therefore enters the key, and
everything a published score rests on is digested into the manifest beside it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from memoket_kite.pipeline.compile_plan import _provider_cache_identity

SCHEMA = 4  # bump whenever verdict parsing, the prompt protocol OR a bound digest changes
LEGACY_SCHEMA = 2  # predates framed source digests, so `results_sha` cannot be recomputed
# A schema number alone cannot separate two source-digest encodings that shared
# it. Manifests name their encoding, and a retired encoding is listed here so
# its artifacts are rejected as unverifiable rather than read as tampering.
SUPERSEDED_ALGORITHMS = frozenset({"framed-name-sha256"})
DIGEST_ALGORITHM = "length-framed-name-content-sha256-v1"


def _file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16] if path.exists() else ""


def read_snapshot(paths) -> dict:
    """Read every source file once; everything downstream uses this copy.

    Re-reading a file to digest it after judging opens a window for a
    concurrent evaluator to append to it: the guard would pass against one
    state of the file while the manifest bound a later one. A single read
    closes that window, and the name collision check keeps the snapshot's
    filename keys unambiguous when sources come from several directories.
    """
    snapshot: dict[str, bytes] = {}
    for raw in paths:
        path = Path(raw)
        if not path.exists():
            raise SystemExit(f"{path} disappeared before it could be judged")
        if path.name in snapshot:
            raise SystemExit(f"two source files are both named {path.name}")
        snapshot[path.name] = path.read_bytes()
    return snapshot


def snapshot_digest(snapshot: dict) -> str:
    """Digest of an already-read snapshot; see `source_digest` for the framing."""
    parts = []
    for name in sorted(snapshot):
        content = hashlib.sha256(snapshot[name]).hexdigest()
        # Length-prefix every field: a colon-and-newline delimiter can be
        # forged by a filename, since POSIX allows both.
        parts.append(f"{len(name)}:{name}{len(content)}:{content}")
    return hashlib.sha256("".join(parts).encode("utf-8")).hexdigest()[:32]


def source_digest(paths) -> str:
    """Digest of the answer files a verdict set was produced from.

    LoCoMo writes one file per conversation, so no single path identifies the
    source and the digest has to cover the whole set. It binds the answer bytes
    themselves and not the run manifest, which only describes the run: binding
    a description would leave the answers free to be swapped underneath it.

    Every field is length-prefixed. Plain concatenation of name and content
    makes a file `a` holding `bc` indistinguishable from one called `ab`
    holding `c`, and a `name:sha` delimiter only moves the ambiguity into
    filenames, which may themselves contain colons and newlines.
    """
    return snapshot_digest(read_snapshot(paths))


def checkpoint(cache: dict, path: Path, *, every: int = 25) -> None:
    """Persist the verdicts paid for so far, atomically, every `every` entries.

    Verdicts held only in memory until the final question are lost in full to a
    crash part-way through, and the retry has to buy them from the judge again.
    Checkpointing bounds that loss to the entries added since the last write,
    and the write is atomic so an interrupted checkpoint cannot corrupt the
    cache it is extending.
    """
    if len(cache) % every:
        return
    from benchmarks.common.publish import atomic_write

    atomic_write(path, json.dumps(cache, indent=2, sort_keys=True) + "\n")


def judge_cache_key(prompt: str, model: str) -> str:
    """Identity of one judging call: the rendered prompt and who answers it."""
    payload = "\x1f".join((str(SCHEMA), model, _provider_cache_identity(), prompt))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def write_manifest(
    result_dir: Path,
    *,
    model: str,
    source,
    judged: Path,
    protocol: str,
    run: Path,
    score: Path,
    sealed: dict[Path, bytes] | None = None,
) -> dict:
    """Record who judged these answers, beside the verdicts themselves.

    `sealed` maps a path to the exact bytes the caller just wrote there. Any
    path it covers is digested from those bytes instead of by re-reading the
    file: a re-read binds whatever is on disk at that instant, which after a
    concurrent writer is not what this scorer produced.

    Without a manifest, `--offline` reports whatever judge model the caller
    names over verdicts that may have come from another one, and a re-judge
    overwrites the only evidence of the previous judge. A published accuracy
    has to say both who produced it and which system produced the answers, so
    the seal covers the run manifest and the score as well as the source.
    Binding the source alone would leave "these verdicts belong to those
    answers" verifiable while "that score came from this build" is not, and the
    run manifest could then be rewritten to name a different system, diff or
    model with every check still passing.
    """
    for name, path in (("run manifest", run), ("score", score)):
        if not path.exists():
            raise SystemExit(
                f"cannot seal {result_dir.name}: its {name} ({path.name}) does not exist, "
                f"so the seal would bind nothing and every later check would reject it"
            )
    sealed = sealed or {}

    def digest_of(path: Path) -> str:
        if path in sealed:
            return hashlib.sha256(sealed[path]).hexdigest()[:16]
        return _file_digest(path)

    record = {
        "schema": SCHEMA,
        "source_digest_algorithm": DIGEST_ALGORITHM,
        "judge_model": model,
        "provider": _provider_cache_identity(),
        "protocol_sha": hashlib.sha256(protocol.encode("utf-8")).hexdigest()[:16],
        "results_sha": (
            snapshot_digest(source)
            if isinstance(source, dict)
            else source_digest(source if isinstance(source, (list, tuple)) else [source])
        ),
        "judged_sha": digest_of(judged),
        "run_manifest_sha": digest_of(run),
        # Readers consume the score file directly, so it is bound too: an
        # unbound score.json can be edited to any headline number while every
        # other digest in this record still verifies.
        "score_sha": digest_of(score),
    }
    # The seal must land whole: a truncated manifest makes `read_manifest()`
    # raise, and the overwrite guard then refuses the rerun that would repair
    # it, so the write goes through the atomic replace.
    from benchmarks.common.publish import atomic_write

    atomic_write(result_dir / "judge_manifest.json", json.dumps(record, indent=2) + "\n")
    return record


def read_manifest(result_dir: Path) -> dict | None:
    path = result_dir / "judge_manifest.json"
    return json.loads(path.read_text()) if path.exists() else None


def check_offline(
    result_dir: Path,
    model: str,
    *,
    source,
    judged: Path,
    protocol: str,
    run: Path,
    score: Path,
    allow_legacy: bool = False,
) -> tuple[str, bool, bytes]:
    """The judge that actually produced the stored verdicts, re-verified.

    Naming the judge is not enough: the verdict file, the answers behind it and
    the rubric can all be replaced after the fact. Recompute every digest the
    manifest claims and refuse the score if any of them moved.

    Returns the verdict bytes it verified. Handing back a path instead would
    let the caller reopen the file and score content this check never saw,
    which is the substitution the check exists to catch.
    """
    weak = False
    verdicts = judged.read_bytes() if judged.exists() else b""
    recorded = read_manifest(result_dir)
    if recorded is None:
        raise SystemExit(
            f"{result_dir.name} has no judge manifest, so who produced these "
            f"verdicts is unknown; re-judge under a fresh --tag"
        )
    if recorded["judge_model"] != model:
        raise SystemExit(
            f"{result_dir.name} was judged by {recorded['judge_model']}, not {model}; "
            f"pass --judge-model {recorded['judge_model']} or re-judge under a new --tag"
        )
    schema = recorded.get("schema")
    algorithm = recorded.get("source_digest_algorithm")
    if schema == SCHEMA:
        if algorithm in SUPERSEDED_ALGORITHMS:
            raise SystemExit(
                f"{result_dir.name} was judged with source digest {algorithm!r}, which "
                f"this version replaced; its source binding cannot be recomputed, so "
                f"re-judge under a fresh --tag"
            )
        if algorithm != DIGEST_ALGORITHM:
            # A current-schema manifest that cannot name its digest is either
            # corrupt or edited. Selecting the weak path on a missing field
            # would let anyone downgrade verification by deleting one key.
            raise SystemExit(
                f"{result_dir.name} claims schema {SCHEMA} but names source digest "
                f"algorithm {algorithm!r}; refusing to verify it"
            )
        for required in ("run_manifest_sha", "score_sha"):
            if not recorded.get(required):
                # Verifying a field only when it happens to be present is the
                # same fail-open as selecting the legacy path on a missing
                # algorithm: deleting one key would remove the check.
                raise SystemExit(
                    f"{result_dir.name} records no {required}; this artifact cannot be "
                    f"verified under schema {SCHEMA}, so re-judge under a fresh --tag"
                )
        # `provider` is deliberately absent: this is the OFFLINE path, which
        # recomputes a score from stored verdicts and makes no model call.
        # Comparing the CALLER's provider environment against the sealed one
        # would fail any third party whose own OPENAI_BASE_URL differs, on a
        # comparison that says nothing about the artifact. What the sealed run
        # used is still recorded in, and verified through, the digests below.
        checked = (
            "protocol_sha",
            "results_sha",
            "judged_sha",
            "run_manifest_sha",
            "score_sha",
        )
    elif schema == LEGACY_SCHEMA:
        # These manifests carry an unframed source digest, so `results_sha`
        # cannot be recomputed here. Everything else must still match, and the
        # gap is returned as `weak` so callers record it rather than print it.
        if not allow_legacy:
            raise SystemExit(
                f"{result_dir.name} was judged under schema {schema} whose source "
                f"binding cannot be recomputed; pass --allow-legacy to score it anyway"
            )
        weak = True
        checked = ("protocol_sha", "judged_sha")
    else:
        raise SystemExit(
            f"{result_dir.name} has judge manifest schema {schema!r}, which this "
            f"scorer does not know how to verify"
        )
    current = {
        "provider": _provider_cache_identity(),
        "protocol_sha": hashlib.sha256(protocol.encode("utf-8")).hexdigest()[:16],
        "results_sha": source_digest(source if isinstance(source, (list, tuple)) else [source]),
        "judged_sha": hashlib.sha256(verdicts).hexdigest()[:16] if verdicts else "",
        "run_manifest_sha": _file_digest(run),
        "score_sha": _file_digest(score),
    }
    moved = sorted(k for k in checked if recorded.get(k) != current[k])
    if moved:
        raise SystemExit(
            f"{result_dir.name} no longer matches its judge manifest ({', '.join(moved)} "
            f"changed since judging); re-judge under a fresh --tag"
        )
    return recorded["judge_model"], weak, verdicts


def refuse_overwrite(result_dir: Path, model: str, *, protocol: str = "") -> None:
    """Judging over a complete verdict set destroys the evidence behind a score.

    Any manifest at all blocks a re-judge, whatever it records. Refusing only
    when the model name differs would let a provider switch, a reworded rubric
    or a schema bump replace `judged.jsonl` and its manifest under an unchanged
    name; the fields collected here only explain how the two judgings differ,
    they do not decide the refusal. A different judge needs a different tag.
    """
    recorded = read_manifest(result_dir)
    if not recorded:
        return
    differs = [
        name
        for name, value in (
            ("judge_model", model),
            ("provider", _provider_cache_identity()),
            ("schema", SCHEMA),
            *(
                (("protocol_sha", hashlib.sha256(protocol.encode("utf-8")).hexdigest()[:16]),)
                if protocol
                else ()
            ),
        )
        if recorded.get(name) != value
    ]
    raise SystemExit(
        f"{result_dir.name} already holds verdicts from {recorded['judge_model']}"
        + (f" ({', '.join(differs)} differ)" if differs else "")
        + "; judging again would overwrite them. Use a new --tag."
    )
