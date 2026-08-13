# KITE benchmarks

Benchmark code is separate from the installable package. Each public benchmark
has the same readable stage layout:

| File | Responsibility |
|---|---|
| `adapter.py` | Convert the official dataset format into conversation episodes |
| `profile.py` | Freeze benchmark prompts, vocabulary, and explicit pipeline settings |
| `protocol.py` | Preserve the official judging rules and deterministic metrics |
| `build.py` | Build complete Codebooks |
| `evaluate.py` | Answer benchmark questions, with explicit resume support |
| `score.py` | Judge results or recompute an existing judged run offline |

## Benchmark policy layer

A benchmark binding may enable deterministic, gold-blind answer policies that
belong to the evaluation protocol rather than to the library — the premise
refusal and the saturated-basis count repair in
`memoket_kite.pipeline.postproc`. Three rules keep the layer honest:

1. **Gold-blind by construction.** A policy reads the question, the answer's
   own text, and the deterministic verdicts the answer stage recorded — never
   question ids, gold answers, or judge output.
2. **Declared, not ambient.** Which policies a binding enables is set in its
   profile (`POSTPROC_RULES`) and recorded in every run manifest, so a
   published score always names the policy set that produced it.
3. **Reported as what they are.** These are protocol-specific policies,
   isolated from the library's own defaults and fingerprinted in every run
   manifest — not universal semantic repairs, and not claimed as such.

### Question predicates

A binding recognises two question shapes the library's own predicates leave
narrow: one that asks for a judgement without an explicit speech act ("could
there be a reason…"), and one that points back at an earlier exchange ("our
previous conversation", "remind me", "you mentioned"). Both read question text
only, never an id, a gold answer, or judge output, and both live under
`benchmarks/` rather than inside the installable package. Each run manifest
records their digests, so a score always names the predicates it ran under.

`common/paths.py` contains repository artifact paths. `tools/leak_check.py` is
the only analysis gate retained in the release tree. Dataset, Codebook, cache,
and result files always belong under the Git-ignored `artifacts/` directory.

## Pinned datasets

- **LoCoMo:** the ten-conversation `data/locomo10.json` release.
- **LongMemEval:** the current official `longmemeval_s_cleaned.json` release.

Exact upstream revisions, download URLs, and SHA256 values are recorded in
[`reproduce/manifest.json`](reproduce/manifest.json). Download and verify both:

```bash
python -m benchmarks.reproduce.prepare datasets
```

## Stage commands

```bash
python -m benchmarks.locomo.build --help
python -m benchmarks.locomo.evaluate --help
python -m benchmarks.locomo.score --help

python -m benchmarks.longmemeval.build --help
python -m benchmarks.longmemeval.evaluate --help
python -m benchmarks.longmemeval.score --help
```

LongMemEval's build profile explicitly enables two finalization stages after
Fact extraction and topic/entity consolidation:

```text
align repeated real-world instances → refine topic assignments → atomic publish
```

They run once for every LongMemEval Codebook. They are never selected by
question type or gold label and are not query-time post-processing. LoCoMo does
not enable either stage.

## Reproduction paths

For a full local reproduction, configure the LLM endpoint and run the two
scripts under `reproduce/`. The workflow fetches the pinned upstream datasets
and rebuilds the evaluation under the local `artifacts/` tree. See
[`docs/reproducibility.md`](../docs/reproducibility.md) for the complete contract.
