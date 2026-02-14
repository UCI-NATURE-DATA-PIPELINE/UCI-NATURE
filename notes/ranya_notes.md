**Last updated:** Feb 2026  
---

## Project Goal

- Process **100,000+ unprocessed wildlife images** in Google Drive
- Build a **reliable, low-cost pipeline**
- Output a **usable spreadsheet** for non-technical users

**Key constraints**
- ML accuracy is secondary
- Pipeline correctness > model performance
- Species classification is future work

---

## Pipeline Overview

index → download → manifest → ML → merge/export

- **Index:** collect image file IDs + full Drive paths
- **Download:** download by file ID, preserve folder structure (resume/skip)
- **Manifest:** create per-image rows (file_id + local_path) for ML + matching
- **ML:** run MegaDetector (blank vs animal) and convert to per-image CSV
- **Export:** output final CSV for partner

---

## Repository Structure

secrets/
service_account.json

scripts/
build_index.py
download_drive.py
make_manifest.py
ml/
run_megadetector.py
(convert outputs script)

data/
staging/  # mirrors Drive folders (download target)
outputs/
drive_index.csv
download_log.csv
.download_progress.csv
manifest.csv
md_results.json
ml_outputs.csv
inference_errors.csv

---

## Script Responsibilities

### build_index.py
- Recursively scans Google Drive
- Images only (no folders, no spreadsheets)
- Captures:
  - file_id
  - file_name
  - mime_type
  - drive_path
- Output:
  - data/outputs/drive_index.csv

---

### download_drive.py
- Reads drive_index.csv
- Downloads images using file_id
- Saves to data/staging/ using Drive path
- Avoids filename collisions (file_id__original_name)
- Skips already-downloaded files (staging + progress file)
- Retry/resume tracking:
  - data/outputs/.download_progress.csv
- Output:
  - data/outputs/download_log.csv

---

### make_manifest.py
- Scans downloaded images under data/staging/
- Writes manifest rows for ML + matching back to file_id
- Output:
  - data/outputs/manifest.csv

---

### scripts/ml/run_megadetector.py
- Runs MegaDetector on images in data/staging/
- Output:
  - data/outputs/md_results.json

---

### ML output conversion (provider-based)
- Reads:
  - manifest.csv
  - md_results.json
- Produces per-image results keyed by file_id
- Logs unmatched files + failures
- Output:
  - data/outputs/ml_outputs.csv
  - data/outputs/inference_errors.csv

---

## Output Columns

**Current / Planned**
- file_id
- camera_name (from folder path)
- date
- time
- has_animal
- is_blank
- species (placeholder)
- count
- model_certainty

---

## Dependencies

- Python 3.10+
- Google Drive API
- Service account key in secrets/

**Packages**
- google-api-python-client
- google-auth
- pillow / exif tools
- megadetector

---

## Run Commands

Full run (manual):
python scripts/pipeline/build_index.py
python scripts/pipeline/download_drive.py
python scripts/pipeline/make_manifest.py
python scripts/ml/run_megadetector.py
python scripts/ml/convert_outputs.py  # or your provider-based converter

---

## Current Status

**Working**
- Drive indexing (recursive)
- File ID–based downloads
- Folder structure preserved (Drive path mirrored)
- Resume/skip via .download_progress.csv
- MegaDetector writes md_results.json
- ml_outputs.csv generated (blank vs animal) + inference_errors.csv
