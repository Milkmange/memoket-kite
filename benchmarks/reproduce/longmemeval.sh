#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

MODEL="${MODEL:-gpt-4.1-mini}"
BUILD_WORKERS="${BUILD_WORKERS:-8}"
EVAL_WORKERS="${EVAL_WORKERS:-4}"
# The tag the packager will read, taken from the manifest so a run made by
# following this script is the run the release ships. Overriding TAG produces
# results the packager ignores, which is what an experiment wants.
TAG="${TAG:-$("${PYTHON_BOOTSTRAP:-$(command -v python3 || command -v python)}" -c "
import json, pathlib, re, sys
manifest = json.loads(pathlib.Path('benchmarks/reproduce/manifest.json').read_text())
path = manifest['benchmarks']['longmemeval']['result_path']
sys.stdout.write(re.sub(r'^longmemeval-', '', pathlib.PurePosixPath(path).parent.name))
")}"
# Honour the same artifact root the Python tooling reads.
ARTIFACTS="${KITE_ARTIFACTS_DIR:-artifacts}"
# `python` is absent on installs that ship only `python3`; the stage commands
# below run under whichever this resolves to, so a virtualenv still wins.
PYTHON="${PYTHON:-$(command -v python || command -v python3)}"
MODE="${1:-full}"
RESUME=()
if [[ "$MODE" == "resume" ]]; then
  RESUME=(--resume)
elif [[ "$MODE" != "full" ]]; then
  echo "usage: $0 [full|resume]" >&2
  exit 2
fi

echo "benchmark=longmemeval dataset=$ARTIFACTS/datasets/longmemeval/longmemeval_s_cleaned.json"
echo "model=$MODEL build_workers=$BUILD_WORKERS eval_workers=$EVAL_WORKERS tag=$TAG mode=$MODE"

"$PYTHON" -m benchmarks.longmemeval.build \
  --n 500 --workers "$BUILD_WORKERS" --model "$MODEL" ${RESUME[@]+"${RESUME[@]}"}

"$PYTHON" -m benchmarks.longmemeval.evaluate \
  --n 500 --workers "$EVAL_WORKERS" --model "$MODEL" --answer-model "$MODEL" --tag "$TAG" \
  --plan-cache "$ARTIFACTS/cache/plans/longmemeval-$TAG" ${RESUME[@]+"${RESUME[@]}"}

"$PYTHON" -m benchmarks.longmemeval.score \
  --tag "$TAG" --judge-model "$MODEL" --workers "$EVAL_WORKERS"
