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

Run pipeline (manual scripts):
python scripts/ml/run_speciesnet.py
python scripts/ml/postprocess_speciesnet.py
python scripts/ml/run_inference.py --provider speciesnet
python scripts/pipeline/extract_metadata.py
python scripts/pipeline/make_output.py
python scripts/pipeline/validate_output.py