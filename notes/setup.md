## setup instructions

Prereqs:
- Python 3.11
- macOS/Linux recommended

Create venv:
python3.11 -m venv .venv311
source .venv311/bin/activate

Install deps:
pip install -r requirements/requirements.lock 
pip install -r requirements/requirements.txt
pip install fastapi uvicorn

SpeciesNet note (if needed):
pip install speciesnet --use-pep517

Quick sanity check:
python -c "import speciesnet; print('speciesnet ok')"

Supported workflow A: legacy terminal full pipeline
python3.11 scripts/pipeline/run_pipeline.py

Expected input:
- working service account JSON at secrets/inf191a-uci-nature-sa.json
- Drive folder shared with that service account

Supported workflow B: UI-backed workflow
python3.11 -m uvicorn ui.backend.main:app --reload --host 127.0.0.1 --port 8000
cd ui && python3 -m http.server 3000

Docker deployment assets:
- docker/docker-compose.yml
- docker/Dockerfile.backend
- docker/Dockerfile.frontend
- docker/Caddyfile
- docker/nginx.conf

Expected input:
- images already copied into data/staging/

Current UI path limitations:
- starts from data/staging only
- export route is artifact-backed but Drive upload is not fully wired
- exclude_humans is not fully enforced in exported rows yet

Run manual steps in order:
python3.11 scripts/pipeline/build_index.py
python3.11 scripts/pipeline/download_drive.py
python3.11 scripts/pipeline/make_manifest.py
python3.11 scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
python3.11 scripts/ml/run_speciesnet.py
python3.11 scripts/ml/postprocess_speciesnet.py
python3.11 scripts/ml/run_inference.py --provider speciesnet
python3.11 scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
python3.11 scripts/pipeline/make_output.py
python3.11 scripts/pipeline/validate_output.py
