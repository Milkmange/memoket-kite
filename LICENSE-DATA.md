# Data licensing

The Apache-2.0 licence in [`LICENSE`](LICENSE) covers the source code in this
repository. It does **not** cover benchmark data or anything derived from it.
Benchmark datasets and locally derived artifacts remain outside KITE's source
and package distributions; the terms below apply when users build them locally.

## Source datasets

| Dataset | Licence | Copyright | Source | Full text |
|---|---|---|---|---|
| LoCoMo (`locomo10.json`) | CC BY-NC 4.0 | Snap Inc. | [snap-research/locomo](https://github.com/snap-research/locomo) | [`licenses/third-party/LoCoMo-CC-BY-NC-4.0.txt`](licenses/third-party/LoCoMo-CC-BY-NC-4.0.txt) |
| LongMemEval-S (cleaned) | MIT | Copyright (c) 2024 Di Wu | [xiaowu0162/LongMemEval](https://github.com/xiaowu0162/LongMemEval), cleaned copy at [xiaowu0162/longmemeval-cleaned](https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned) | [`licenses/third-party/LongMemEval-MIT.txt`](licenses/third-party/LongMemEval-MIT.txt) |

The full upstream licence texts are carried verbatim in
[`licenses/third-party/`](licenses/third-party/) so users can identify the terms
that apply before obtaining a dataset or building derived artifacts.

Neither dataset is redistributed in this repository. Both are pinned by
revision and SHA-256 in [`benchmarks/reproduce/manifest.json`](benchmarks/reproduce/manifest.json)
and fetched from their own sources.

## Modifications

- LongMemEval-S is used in the cleaned revision pinned in the manifest; KITE
  does not alter it.
- LoCoMo is used at the pinned revision, unaltered.
- What KITE adds is derived: the codebooks below, and the run outputs that
  quote the source conversations.

## Derived codebooks

A codebook is the XML store KITE extracts from a conversation. Its content is
derived from the conversation it was built from, so **a codebook carries the
licence of the dataset it came from, not Apache-2.0**:

- `artifacts/codebooks/locomo/**` — derived from LoCoMo, therefore
  **CC BY-NC 4.0**: attribution required, and no commercial use.
- `artifacts/codebooks/longmemeval/**` — derived from LongMemEval-S, therefore
  MIT.

The same applies to run outputs that quote the source text — `results_*.jsonl`,
`judged.jsonl` and the evidence packs recorded in them.

If you need KITE for commercial work, the code is Apache-2.0 and free to use;
build your Codebooks from data whose terms permit that use.

## Brand assets

The images under `assets/` are not covered by the Apache-2.0 licence of this
repository's code. The Memoket and KITE names, logos, and banner artwork are
trademarks of their owner and may not be reused to imply affiliation. The App
Store and Google Play badges are Apple's and Google's respective trademarked
artwork, included solely to link to the Memoket apps under each store's badge
usage guidelines.
