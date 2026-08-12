# Reproducibility

KITE separates dataset inputs, generated artifacts, and scoring code so every
published result can be traced to exact bytes.

## Pinned inputs

[`benchmarks/reproduce/manifest.json`](../benchmarks/reproduce/manifest.json)
records the official upstream revision, immutable download URL, local path, and
SHA256 for LoCoMo and cleaned LongMemEval_S. Raw datasets are downloaded from
their publishers and are never redistributed in a KITE release.

```bash
python -m benchmarks.reproduce.prepare datasets
```

The command downloads to a temporary file, verifies its SHA256, and only then
moves it into `artifacts/datasets/`.

## Full reproduction

```bash
cp .env.example .env
# Set OPENAI_API_KEY; optionally set OPENAI_BASE_URL.
source .env

bash benchmarks/reproduce/locomo.sh
bash benchmarks/reproduce/longmemeval.sh
```

Each script prints the dataset path, model IDs, worker count, output directory,
and stage before doing work. Build and evaluation commands support `--resume`;
any failed ID is written to `failed.txt` and the process exits nonzero. A retry
must be explicit—scripts do not hide errors or retry indefinitely.

The complete LongMemEval Codebook build is:

```text
extract Facts
→ consolidate topics and entities
→ align repeated real-world instances
→ refine topic assignments against the final taxonomy
→ atomically publish the Codebook
```

Both finalization stages are enabled visibly in
`benchmarks/longmemeval/profile.py` and run uniformly for all 500 haystacks.

## Five-minute offline verification

After `v0.1.0` release assets are published:

```bash
python -m benchmarks.reproduce.prepare datasets
python -m benchmarks.reproduce.prepare artifacts
python -m benchmarks.reproduce.verify locomo
python -m benchmarks.reproduce.verify longmemeval
```

The datasets come first, and are not optional: every sealed run records a
`corpus_sha` taken over the dataset *and* the codebooks, and the verifier
checks it, so fetching the artifacts alone leaves nothing to check them
against.

These commands verify release-asset hashes, count Codebooks and result rows,
and recompute the reported aggregate from `judged.jsonl` through its judge
seal. They make no LLM call.

## Release artifacts

The release package command expects complete Codebooks, pinned plan caches,
judged results, and a built wheel/source distribution:

```bash
python -m build
python -m benchmarks.reproduce.package v0.1.0
# After the tag workflow creates the GitHub Release, upload exactly the
# files the sealed manifest pins -- never a directory glob, which would
# also publish anything else that happens to be in the staging directory:
cd artifacts/release
gh release upload v0.1.0 \
  artifact-manifest.json SHA256SUMS \
  memoket-kite-v0.1.0-locomo.tar.gz \
  memoket-kite-v0.1.0-longmemeval-cleaned.tar.gz \
  memoket_kite-0.1.0-py3-none-any.whl \
  memoket_kite-0.1.0.tar.gz
```

Keep the release as a draft until CI is green and the four offline verification
commands above pass from a fresh clone. Then compare the uploaded files with
`SHA256SUMS` and make the draft public explicitly:

```bash
gh release download v0.1.0 --dir /tmp/kite-v0.1.0-release
cd /tmp/kite-v0.1.0-release
sha256sum --check SHA256SUMS
gh release edit v0.1.0 --draft=false
```

Publishing the draft is deliberately a separate human action: the tag workflow
creates an invisible draft before the sealed benchmark artifacts exist, and
must not make that incomplete state public.

It produces:

- `memoket-kite-v0.1.0-locomo.tar.gz`
- `memoket-kite-v0.1.0-longmemeval-cleaned.tar.gz`
- `artifact-manifest.json`
- `SHA256SUMS`
- the wheel and source distribution copied from `dist/`

The archive command uses an explicit allowlist and never includes raw datasets,
private corpora, or unrelated historical runs. Packaging fails if counts or
required files do not match the manifest.

## Publishing a score

The tracked manifest pins each benchmark's `score`, and keeps the release
commit unset until both full runs finish against the pinned inputs. An
`asset_sha256` appears once packaging has built the archive it describes:
packaging then verifies a pinned digest instead of overwriting it, so a digest
is either correct or absent, never stale. Fill values only from the generated
`artifact-manifest.json`, then rerun both offline verification
commands in a fresh clone. This prevents an old score from being paired with a
new dataset or artifact set.
