# Contributing to KITE

KITE is research software. Clear behavior, traceable evidence, and reproducible
evaluation take priority over expanding the API surface.

## Development setup

```bash
python -m pip install -e ".[dev,benchmark]"
ruff check src tests benchmarks examples
ruff format --check src tests benchmarks examples
pytest
```

## Pull requests

- Keep algorithm changes separate from mechanical cleanup and documentation.
- Add deterministic regression coverage for retrieval, trace, serialization,
  and public API changes.
- Do not introduce import-time file scans, environment mutations, network
  calls, or output.
- Keep all generated datasets, Codebooks, caches, results, and reports under
  `artifacts/`; never commit credentials or private absolute paths.
- Use the existing public `Memory.load/remember/recall/answer` contract unless
  an API proposal has been discussed first.

## Benchmark and data changes

Benchmark claims must identify the exact dataset revision and SHA256, model IDs,
prompt/protocol changes, denominator, and generated artifact hashes. Update the
reproduction manifest and add an offline metric test. Do not compare scores
from different dataset revisions as if they were the same experiment.

Before adding any corpus or fixture, confirm that its license permits
redistribution. Official benchmark datasets remain external; KITE releases
contain only generated Codebooks, caches, results, manifests, and checksums.

## Security and privacy

Remove private conversational content from bug reports and fixtures. Report
vulnerabilities through the process in [`SECURITY.md`](SECURITY.md).
