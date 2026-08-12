"""Judge and score cleaned LongMemEval result rows."""

from __future__ import annotations

import argparse
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from benchmarks.common import canonical, judging, manifest, publish, singlewriter
from benchmarks.common.judging import judge_cache_key
from benchmarks.common.paths import CODEBOOKS_ROOT, RESULTS_ROOT, safe_tag
from benchmarks.longmemeval.evaluate import DATASET
from benchmarks.longmemeval.protocol import JUDGE_PROMPTS, question_type, summarize
from memoket_kite.providers.llm import llm


def _print_summary(metrics: dict, *, model: str) -> None:
    overall = metrics["overall"]
    print(f"\n== LongMemEval cleaned ({overall['n']} QA, judge={model}) ==")
    print(f"{'type':<28}{'n':>6}{'accuracy':>11}{'ev-rec':>10}")
    for name, values in metrics["question_types"].items():
        evidence = values["evidence_recall"]
        evidence_text = "n/a" if evidence is None else f"{evidence:.3f}"
        print(f"{name:<28}{values['n']:>6}{values['accuracy']:>11.3f}{evidence_text:>10}")
    evidence = overall["evidence_recall"]
    evidence_text = "n/a" if evidence is None else f"{evidence:.3f}"
    print(f"{'TOTAL':<28}{overall['n']:>6}{overall['accuracy']:>11.3f}{evidence_text:>10}")


def _corpus_moved(result_dir: Path, recorded_sha, allow_legacy: bool) -> bool:
    """The corpus that produced these answers must still be the one on disk.

    Judging costs money and publishes a score under the run's manifest. If the
    dataset or a codebook moved since the run, that manifest no longer
    describes what is about to be scored. Returns whether the binding is
    unverifiable rather than merely absent.
    """
    current = manifest.corpus_digest([DATASET, CODEBOOKS_ROOT / "longmemeval"])
    if not recorded_sha:
        # Skipping the check when the field is absent would fail open: an
        # artifact could escape the binding simply by not declaring what it
        # read. A run that records no corpus_sha is scoreable only under
        # --allow-legacy, and the score then says so.
        if not allow_legacy:
            raise SystemExit(
                f"{result_dir.name} declares no corpus_sha, so what it read cannot be "
                f"verified; re-run it, or score it with --allow-legacy"
            )
        return True
    if recorded_sha != current:
        raise SystemExit(
            f"{result_dir.name} was run against corpus {recorded_sha}, but the corpus on "
            f"disk is now {current}; restore it or re-run before scoring"
        )
    return False


def _canonical(
    records: list[dict], result_dir: Path, data: list[dict], allow_legacy: bool = False
) -> tuple[bool, list[dict]]:
    """Hold the results to the corpus and take the judge's inputs from it.

    Returns whether the corpus binding had to be waived, so the score can say
    so instead of reading as fully verified.

    The row supplies its question id and the system's answer; the question, the
    gold and the type come from the frozen dataset. Merely comparing the row's
    copies against the dataset would leave a forged gold scoreable as long as
    the ids line up.
    """
    path = result_dir / "manifest.json"
    if not path.exists():
        raise SystemExit(f"{result_dir.name} has no run manifest; cannot tell if it finished")
    recorded = json.loads(path.read_text())
    declared = recorded.get("effective_n")
    if declared is None:
        raise SystemExit(
            f"{result_dir.name} predates effective_n; its coverage cannot be verified, "
            f"so re-run it before scoring"
        )
    if not recorded.get("selected_sha"):
        raise SystemExit(
            f"{result_dir.name} records no selected_sha; its question set cannot be "
            f"verified, so re-run it before scoring"
        )
    answered = [record["question_id"] for record in records]
    if len(answered) != declared:
        raise SystemExit(
            f"{result_dir.name} answered {len(answered)} of the {declared} questions it "
            f"declared; finish the run (--resume) before scoring it"
        )
    if recorded["selected_sha"] != manifest.question_digest(answered):
        raise SystemExit(
            f"{result_dir.name} answered {declared} questions, but not the ones it "
            f"selected; re-run it under a fresh --tag"
        )
    corpus_unverified = _corpus_moved(result_dir, recorded.get("corpus_sha"), allow_legacy)
    expected = {item["question_id"]: item for item in data if item["question_id"] in set(answered)}
    return corpus_unverified, canonical.reconcile(
        records,
        expected,
        key_of=lambda row: row["question_id"],
        fields=(
            ("question", "question"),
            ("gold", "answer"),
            ("question_type", "question_type"),
            # Evidence recall is scored against this. Taken from the row, the
            # system under test would choose its own denominator: echoing back
            # the sessions it happened to retrieve reads as perfect recall.
            ("answer_session_ids", "answer_session_ids"),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="v0.1.0")
    parser.add_argument("--judge-model", default="gpt-4.1-mini")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--results", type=Path)
    parser.add_argument(
        "--allow-legacy",
        action="store_true",
        help="score an artifact whose judge manifest predates framed source digests",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="recompute metrics from an existing judged.jsonl without LLM calls",
    )
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be a positive integer")
    if args.results is None:
        try:
            args.tag = safe_tag(args.tag)
        except ValueError as error:
            parser.error(str(error))
    # The corpus, not the results file, supplies every input the judge uses.
    with DATASET.open(encoding="utf-8") as stream:
        data = json.load(stream)
    result_dir = args.results or RESULTS_ROOT / f"longmemeval-{args.tag}"
    results_path = result_dir / "results.jsonl"
    judged_path = result_dir / "judged.jsonl"
    # Assigned by the offline check; an online run has verified nothing to
    # weaken. Bound before either branch so the summary below reads a defined
    # value on both paths, after the judging has been paid for.
    source_binding_weak = False
    corpus_unverified = False
    # One scorer per tag. The drift check and the seal both assume this
    # process is the only writer; two concurrent scorers defeat each
    # other's guards, and `refuse_overwrite` is a no-op in exactly the
    # state two fresh scorers share.
    with singlewriter.held(result_dir, purpose="scoring"):
        if args.offline:
            if not judged_path.exists():
                raise SystemExit(f"missing judged results: {judged_path}")
            # Name the judge in the artifact, never the one on the command line.
            _judge_model, source_binding_weak, verified = judging.check_offline(
                result_dir,
                args.judge_model,
                source=results_path,
                judged=judged_path,
                protocol=json.dumps(JUDGE_PROMPTS, sort_keys=True),
                run=result_dir / "manifest.json",
                score=result_dir / "score.json",
                allow_legacy=args.allow_legacy,
            )
            # These are the bytes `check_offline` verified, handed back rather than
            # re-read: reopening the file would score content the check never saw.
            records = [
                json.loads(line) for line in verified.decode("utf-8").splitlines() if line.strip()
            ]
            # Offline applies the same rule, on the same records, as online.
            corpus_unverified, records = _canonical(records, result_dir, data, args.allow_legacy)
        else:
            if not results_path.exists():
                raise SystemExit(f"missing results: {results_path}")
            # Read the answers ONCE. Parsing, judging and the manifest all consume
            # this copy, so nothing appended mid-run can slip between the guard and
            # the digest the manifest publishes. Judging takes minutes, and the
            # run manifest is likewise sealed from THESE bytes rather than from
            # a second read once judging is over.
            run_path = result_dir / "manifest.json"
            run_bytes = run_path.read_bytes() if run_path.exists() else b""
            observed = publish.observe([run_path, results_path])
            snapshot = judging.read_snapshot([results_path])
            records = [
                json.loads(line)
                for line in snapshot[results_path.name].decode("utf-8").splitlines()
                if line.strip()
            ]
            corpus_unverified, records = _canonical(records, result_dir, data, args.allow_legacy)
            judging.refuse_overwrite(
                result_dir,
                args.judge_model,
                protocol=json.dumps(JUDGE_PROMPTS, sort_keys=True),
            )
            cache_path = result_dir / "judge_cache.json"
            cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
            lock = threading.Lock()

            def judge(record: dict) -> None:
                template = JUDGE_PROMPTS.get(question_type(record), JUDGE_PROMPTS["default"])
                prompt = template.format(q=record["question"], a=record["gold"], r=record["answer"])
                # A verdict belongs to the judge that produced it. The key covers
                # the fully rendered prompt and the model name, so a different
                # judge — or a reworded rubric — cannot reuse the previous label
                # while the report names the new one.
                key = judge_cache_key(prompt, args.judge_model)
                if key in cache:
                    record["ok"] = cache[key]
                    return
                response = llm(prompt, model=args.judge_model)
                verdict = 1.0 if "yes" in response.strip().lower()[:6] else 0.0
                record["ok"] = verdict
                with lock:
                    cache[key] = verdict
                    judging.checkpoint(cache, cache_path)

            with ThreadPoolExecutor(max_workers=args.workers) as executor:
                list(executor.map(judge, records))
            # Atomic, like every checkpoint before it. A plain write here could
            # truncate a complete, already-paid-for cache if the process died
            # mid-write — the one moment the whole round is recoverable from.
            judging.checkpoint(cache, cache_path, every=1)
            metrics = summarize(records)
            metrics["provenance"] = {
                "source_binding": "verified",
                "corpus_binding": "unverified" if corpus_unverified else "verified",
            }
            # One transaction: judged and score land atomically, then the manifest
            # seals them. Its presence is what says the artifact is complete.
            publish.publish(
                result_dir,
                observed=observed,
                sealed={run_path: run_bytes},
                judged="".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records),
                score=metrics,
                manifest=lambda sealed: judging.write_manifest(
                    result_dir,
                    model=args.judge_model,
                    source=snapshot,
                    judged=judged_path,
                    protocol=json.dumps(JUDGE_PROMPTS, sort_keys=True),
                    run=result_dir / "manifest.json",
                    score=result_dir / "score.json",
                    sealed=sealed,
                ),
            )
        if args.offline:
            metrics = summarize(records)
            metrics["provenance"] = {
                "source_binding": "legacy_weak" if source_binding_weak else "verified",
                "corpus_binding": "unverified" if corpus_unverified else "verified",
            }
        if source_binding_weak:
            print("  PROVENANCE: LEGACY / WEAK SOURCE BINDING — not a release-grade result")
        _print_summary(metrics, model=args.judge_model)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
