#!/usr/bin/env bash
set -e

if [ -d ".venv" ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
elif [ -d ".venv311" ]; then
  # shellcheck disable=SC1091
  source .venv311/bin/activate
fi

BATCH=$1
if [ -z "$BATCH" ]; then
  echo "usage: ./run_batch.sh batch_0001.csv"
  exit 1
fi

cp "data/outputs/batches/$BATCH" data/outputs/manifest.csv

python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
python scripts/ml/run_speciesnet.py
python scripts/ml/postprocess_speciesnet.py
python scripts/ml/run_inference.py --provider speciesnet
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
python scripts/pipeline/make_output.py
python scripts/pipeline/validate_output.py
