# Changelog

## 0.1.0 - Unreleased

- Simplified the application API to `Memory.load`, `remember`, `recall`, and
  `answer`; its top-level error is `KiteError`.
- Added atomic single-file session persistence and marked `Memory.remember()`
  as experimental.
- Unified `remember()` and `recall()` on `list[Fact]`; `answer()` returns text.
- Moved Codebook, query, profile, and trace APIs under `memoket_kite.research`.
- Reorganized the symbolic memory core as the installable `memoket-kite`
  distribution with the `memoket_kite` import package.
- Separated benchmark harnesses, documentation, tests, and generated artifacts.
- Added pinned-dataset reproduction, offline score verification, and GitHub
  Release packaging commands for LoCoMo and cleaned LongMemEval.
- Standardized provider configuration on `OPENAI_API_KEY` and optional
  `OPENAI_BASE_URL` without import-time environment loading.
- Added pytest regression coverage, examples, packaging metadata, and CI.
- Preserved the existing symbolic algorithms and benchmark protocols.
- Preserved live facet and typed-entity constraints while pruning dead symbolic
  values, and made equal-score evidence selection deterministic.
- Added a lazy corpus-relative specificity tiebreaker for truncating query pipes,
  so equally relevant rows prefer concrete evidence before `head` or `tail`.
- Lazily cached topic closures and candidate scores within each query execution
  to avoid repeated taxonomy traversal during ranking.
- Fingerprinted the complete compile prompt and compilation settings for plan
  caches so changed Codebook context cannot reuse a stale plan, including
  provider endpoints and entity-to-object bridges used by plan scoring; cache
  files are now published atomically.
- Counted aligned-instance mention units in LongMemEval evidence recall.
- Preserved full LongMemEval unit IDs that contain the Fact separator character.

## Deterministic post-processing and evidence-budget work

- Added a channel ledger (`memoket_kite.pipeline.ledger`) that records, per
  question, the token cost of every contributor to the answer prompt and every
  reader call. Observation-only: pack contents and call topology are unchanged
  with it active, and benchmark records now carry the accounting.
- Added a deterministic, zero-LLM post-processing stage
  (`memoket_kite.pipeline.postproc`) with four certified rules: premise refusal
  for absent-entity questions, hedge canonicalization, saturated-basis
  undercount repair, and zero-answer disclosure. Rules read only the question,
  the answer text, and the verdicts recorded by the answer stage.
- Added `ANSWERABLE_BY_CONSTRUCTION` to the benchmark bindings. Where a
  workload declares a question class answerable, the support check no longer
  downgrades an unsupported answer to a refusal and the premise-refusal rule
  does not fire — a refusal there is a guaranteed miss.
- Bounded evidence admission by both a row count and a token budget, whichever
  binds first, and restored the chronological ordering the answer prompt
  asserts after the retry chain appends rows.
- Added the dual-date annotation to the LoCoMo renderer: an evidence row whose
  event date differs from its session date and whose text carries a relative
  phrase is annotated so the reader does not resolve the phrase a second time.
  LongMemEval enables it by default; LoCoMo ships with it off (`DUAL_DATE`).
- Removed mechanisms that measurement rejected: soft grep matching, span
  widening, render dedup, the support gate, relative-date resolution, and the
  build-stage coverage repair pass.
