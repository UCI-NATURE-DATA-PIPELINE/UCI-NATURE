# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Wildlife camera trap image processing pipeline for UCI Campus Reserves. Automates classification of 100K+ camera trap images stored in Google Drive using SpeciesNet (Google's CameraTrapAI). Replaces manual student intern review with ML-based species identification, burst grouping, and per-camera CSV output.

## Environment Setup

**Python 3.11 is required exactly** — enforced at runtime by `run_pipeline.py`.

```bash
python3.11 -m venv .venv311
source .venv311/bin/activate
pip install --no-deps -r requirements/requirements.lock
pip install speciesnet==5.0.3 --use-pep517 # ML dependencies (torch, onnx, etc.)
```

## Running the Pipeline

**Full pipeline (auto mode — indexes Drive, downloads, processes):**
```bash
python scripts/pipeline/run_pipeline.py
```

**Manual mode (process a local folder of images):**
```bash
python scripts/pipeline/run_pipeline.py --mode manual --folder /path/to/images
```

**Individual steps in order:**
```bash
python scripts/pipeline/build_index.py           # Step 1: Scan Drive → drive_index.csv
python scripts/pipeline/download_drive.py        # Step 2: Download images → data/staging/
python scripts/pipeline/make_manifest.py         # Step 3: Inventory files → manifest.csv
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv  # Step 4: EXIF only → metadata.csv
python scripts/ml/run_speciesnet.py              # Step 5: Run SpeciesNet → speciesnet_results.json
python scripts/ml/postprocess_speciesnet.py      # Step 6: Burst voting (needs metadata.csv) → speciesnet_results.csv
python scripts/ml/run_inference.py --provider speciesnet  # Step 7: JSON→CSV → ml_outputs.csv
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv  # Step 8: Merge ML → metadata.csv
python scripts/pipeline/make_output.py           # Step 9: Per-camera CSVs → by_location/
python scripts/pipeline/validate_output.py       # (Optional) Validate outputs
```

**Single batch shortcut:**
```bash
./run_batch.sh batch_0001.csv
```

**Upload results to Drive (production — requires permission):**
```bash
python scripts/drive_upload/upload_to_drive.py [--overwrite]
```

## No Test Suite or Linting

There is no test framework, linter, or CI/CD configured. Testing is done manually with small batch sizes.

To control how many images are indexed/downloaded, edit `MAX_DOWNLOADS` in `scripts/config.py` (default: 300). This single value is used by both `build_index.py` (as `MAX_ROWS`) and `download_drive.py`. You can also override per-run via CLI: `--max_files` for indexing, `--max_downloads` for downloading.

## Architecture

### Pipeline Flow

```
Google Drive → build_index → download_drive → make_manifest → SpeciesNet → postprocess → run_inference → extract_metadata → make_output → validate_output → upload_to_drive
```

All intermediate data flows through CSV/JSON files in `data/outputs/`. The `file_id` (Google Drive file ID) is the primary key joining data across pipeline steps.

### Key Directories

- `scripts/pipeline/` — Core pipeline steps (indexing, downloading, manifest, metadata, output, validation)
- `scripts/ml/` — ML model runners and postprocessors (SpeciesNet, MegaDetector)
- `scripts/drive_upload/` — Upload final CSVs back to Google Drive (production writes)
- `scripts/config.py` — **Single source of truth** for service account path, Drive folder ID, and `MAX_DOWNLOADS` (controls indexing + download limits)
- `data/staging/` — Downloaded images (gitignored, mirrors Drive folder structure). **Cleared automatically after a successful auto mode run** to free disk space; re-downloads are prevented by `data/outputs/.download_progress.csv`.
- `data/outputs/` — All pipeline outputs: CSVs, JSON, logs, checkpoints (gitignored)
- `secrets/` — Google service account key (gitignored)

### Important Conventions

- **File naming:** Downloaded images use `<file_id>__<original_name>` format — `file_id` is recovered by splitting on `__`
- **Burst detection:** Images from the same camera folder within 300 seconds are grouped into observation bursts with shared `ObservationID`
- **SpeciesNet geofencing:** Hardcoded to `country=USA, admin1_region=CA` in `run_speciesnet.py`
- **Species mapping:** `run_inference.py` maps SpeciesNet taxonomy strings (e.g., `mammalia;carnivora;canidae;canis;canis_latrans`) to simplified labels (e.g., `coyote`)
- **Blank filtering:** `run_inference.py` writes ALL predictions to `ml_outputs.csv`, including blanks (`has_animal=0, species=blank`). This lets `extract_metadata.py` propagate the blank signal into `metadata.csv`, so `make_output.py` can filter them out of the final per-camera CSVs. The final output only contains images with confirmed animal or human detections.
- **Drive upload deduplication:** Uses compound key `DeploymentFolder|Image#` to skip duplicate rows
- **Resume support:** `build_index.py` and `download_drive.py` support `--resume` for checkpoint-based continuation
- **Drive upload is production:** `scripts/drive_upload/` writes directly to Julie's Drive — do not test without permission
