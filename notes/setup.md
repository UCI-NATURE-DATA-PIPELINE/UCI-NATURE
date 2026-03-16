## setup instructions

Prereqs:
- Python 3.11
- macOS/Linux recommended

Create venv:
python3.11 -m venv .venv311
source .venv311/bin/activate

Install deps:
pip install -r requirements/requirements.lock 

SpeciesNet note (if needed):
pip install speciesnet --use-pep517

Quick sanity check:
python -c "import speciesnet; print('speciesnet ok')"

Run full pipeline:
python scripts/pipeline/run_pipeline.py

Run manual steps in order:
python scripts/pipeline/build_index.py
python scripts/pipeline/download_drive.py
python scripts/pipeline/make_manifest.py
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
python scripts/ml/run_speciesnet.py
python scripts/ml/postprocess_speciesnet.py
python scripts/ml/run_inference.py --provider speciesnet
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
python scripts/pipeline/make_output.py
python scripts/pipeline/validate_output.py