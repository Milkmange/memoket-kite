# Reproduce KITE v0.1

The reproduction contract has one source of truth:
[`manifest.json`](manifest.json). It pins official dataset bytes, model IDs,
expected artifact counts, metric names, and—after a full release run—the exact
score and release-asset hashes.

## Verify a published release without an API key

```bash
python -m benchmarks.reproduce.prepare datasets
python -m benchmarks.reproduce.prepare artifacts
python -m benchmarks.reproduce.verify locomo
python -m benchmarks.reproduce.verify longmemeval
```

This path downloads the pinned upstream datasets and generated KITE artifacts.
It checks their hashes, recomputes each dataset-plus-Codebook corpus digest,
counts Codebooks and judged rows, and recomputes the published aggregate
locally.

## Rebuild from official data

```bash
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

## Build release archives

After both full runs and offline score checks succeed:

```bash
python -m build
python -m benchmarks.reproduce.package v0.1.0
```

See [`../../docs/reproducibility.md`](../../docs/reproducibility.md) for the
artifact layout and release checklist.
