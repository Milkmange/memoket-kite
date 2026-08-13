# Reproduce KITE v0.1

The reproduction contract has one source of truth:
[`manifest.json`](manifest.json). It pins official dataset bytes, model IDs,
expected artifact counts, metric names, and reported scores.

## Rebuild from official data

```bash
python -m pip install -e ".[benchmark]"
python -m benchmarks.reproduce.prepare datasets
cp .env.example .env
# Set OPENAI_API_KEY; optionally set OPENAI_BASE_URL.
source .env

bash benchmarks/reproduce/locomo.sh
bash benchmarks/reproduce/longmemeval.sh
```

Use `bash .../locomo.sh resume` or `bash .../longmemeval.sh resume` after an
interrupted run. Failures are never swallowed: the stage exits nonzero and
records failed IDs beside its output.

## Verify the reference reproduction

With the default `TAG` and `MODEL`, the scripts write to the paths declared in
`manifest.json`. After both reference runs succeed:

```bash
python -m benchmarks.reproduce.verify locomo
python -m benchmarks.reproduce.verify longmemeval
```

The verifier checks the reference paths, local manifests, corpus digests,
expected Codebook and row counts, and reported aggregates. For a run made with
a custom `TAG` or `MODEL`, validate its seal and recompute its own metrics with
the corresponding scorer instead:

```bash
python -m benchmarks.locomo.score --tag my-run --judge-model gpt-4.1-mini --offline
python -m benchmarks.longmemeval.score --tag my-run --judge-model gpt-4.1-mini --offline
```

See
[`../../docs/reproducibility.md`](../../docs/reproducibility.md) for the complete
workflow.
