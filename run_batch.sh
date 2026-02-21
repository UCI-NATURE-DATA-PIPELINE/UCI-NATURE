#!/usr/bin/env bash
set -e

source .venv311/bin/activate

BATCH=$1
if [ -z "$BATCH" ]; then
  echo "usage: ./run_batch.sh batch_0001.csv"
  exit 1
fi

cp "data/outputs/batches/$BATCH" data/outputs/manifest.csv

python scripts/pipeline/extract_metadata.py
python scripts/pipeline/make_output.py
python scripts/pipeline/validate_output.py
