# Wildlife Camera Image Processing Pipeline

Automated data pipeline for processing 100,000+ wildlife camera images from UCI Campus Reserves.

Live deployed UI: [https://uci-nature-pipeline.duckdns.org](https://uci-nature-pipeline.duckdns.org)

## Documentation

For full setup instructions, pipeline usage, and troubleshooting, see the documentation:

 [https://ralkhleef.github.io/UCI-NATURE/](https://uci-nature-data-pipeline.github.io/UCI-NATURE-docs/)

## Problem

Current workflow relies on manual review by student interns. Images accumulate faster than they can be processed, creating a backlog of 100,000+ unprocessed images. No project funding available for cloud services.

## Solution

Automated pipeline that retrieves images from Google Drive, extracts metadata, detects duplicates, and classifies images as blank or containing animals.

## Recent updates

- Drive indexing is recursive (nested folders included)
- Downloader reads from `drive_index.csv` and preserves the full Drive folder path locally
- Resumable downloads via `data/outputs/.download_progress.csv` + skip already-downloaded files
- Retry logic with exponential backoff for transient Drive/network failures
- ML output CSV now includes `is_blank` and logs unmatched/failed items to `inference_errors.csv`
- FastAPI UI/backend path can now run the real pipeline in-process from either local staging or a selected Google Drive folder
- Google Drive folder selection in the UI supports My Drive folders, shared folders, shortcut-backed folders, and a manual folder URL/ID fallback

## Current UI App

The current browser app lives in:

- Frontend: `ui/`
- Backend: `ui/backend/`
- Deployment assets: `docker/`

This cleanup keeps the frontend and backend together under `ui/`.
That avoids low-value path churn in static asset loading, Python imports, and deployment wiring while still separating Docker-specific files into their own folder.

### Main UI-backed features

- Google OAuth login in the backend
- Local mode that runs against images already present in `data/staging/`
- Drive mode that stages a selected Google Drive folder into backend staging before running the same pipeline
- Folder selection from the picker or by pasting a Google Drive folder URL or raw folder ID
- Live Drive sync and pipeline status in the UI

---

### Local UI development — macOS / Linux

Run the backend (from the project root `UCI-NATURE/`):

```bash
source .venv311/bin/activate
python3.11 -m uvicorn ui.backend.main:app --reload --host 127.0.0.1 --port 8000
```

Run the static frontend:

```bash
cd ui
python3 -m http.server 3000
```

Then open:

- Frontend: `http://127.0.0.1:3000/`
- Backend API: `http://127.0.0.1:8000/`

---

### Local UI development — Windows (PowerShell)

> **Note:** `source` and `python3.11` are Linux/macOS commands. PowerShell uses different syntax for all of these. Follow the steps below exactly.

#### Step 1 — Allow script execution (one-time setup)

Open PowerShell as a regular user and run:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

#### Step 2 — Create required data directories (one-time setup)

The backend will crash on startup if these folders don't exist. Create them from the project root (`UCI-NATURE\`):

```powershell
mkdir data\staging
mkdir data\local_input
mkdir data\outputs\by_location
```

#### Step 3 — Install missing server dependencies (one-time setup)

`uvicorn` and `fastapi` are not included in `requirements.txt` and must be installed separately:

```powershell
.\.venv311\Scripts\Activate.ps1
pip install uvicorn fastapi python-multipart
```

#### Step 4 — Start the backend

Open a PowerShell terminal, `cd` to the project root (`UCI-NATURE\`), then run:

```powershell
.\.venv311\Scripts\Activate.ps1
python -m uvicorn ui.backend.main:app --reload --host 127.0.0.1 --port 8000
```

> ⚠️ Run uvicorn from the `UCI-NATURE\` root, **not** from inside `ui\`. The module path `ui.backend.main` depends on the root being the working directory.

#### Step 5 — Start the frontend

Open a **second** PowerShell terminal and run:

```powershell
cd ui
python -m http.server 3000
```

Then open `http://127.0.0.1:3000` in your browser.

#### Windows quick-reference cheat sheet

| macOS / Linux | Windows PowerShell |
|---|---|
| `source .venv311/bin/activate` | `.\.venv311\Scripts\Activate.ps1` |
| `python3.11` | `python` |
| `python3` | `python` |
| `mkdir -p a/b/c` | `mkdir a\b\c` |

---

### High-level UI/Drive run flow

1. Sign in and confirm the Google Drive connection.
2. Choose a folder from the Drive dropdown, or use the manual URL/ID fallback.
3. For Drive runs, the backend stages files into `data/staging/`.
4. The pipeline builds the manifest, extracts metadata, runs SpeciesNet, and writes outputs.
5. Results are reviewed in the Dashboard, Review, Validate, and Export pages.

See `DEPLOYMENT.md` for the current EC2/Docker/Caddy deployment workflow.

## Pipeline Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        WILDLIFE IMAGE PIPELINE                          │
└─────────────────────────────────────────────────────────────────────────┘

  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐
  │  INDEX   │───▶│ DOWNLOAD │───▶│ MANIFEST │───▶│INFERENCE │
  │  DRIVE   │    │  IMAGES  │    │  CREATE  │    │  (ML)    │
  └──────────┘    └──────────┘    └──────────┘    └──────────┘
       │               │               │               │
       ▼               ▼               ▼               ▼
  drive_index.csv  download_log.csv  manifest.csv  ml_outputs.csv
                                           │
                                           ▼
                                    ┌──────────┐
                                    │ EXTRACT  │
                                    │ METADATA │
                                    └──────────┘
                                           │
                                           ▼
                                    metadata.csv
                                           │
                                           ▼
                                    ┌──────────┐
                                    │  MERGE   │
                                    │  OUTPUT  │
                                    └──────────┘
                                           │
                                           ▼
                                    ┌──────────┐
                                    │ VALIDATE │
                                    └──────────┘
                                           │
                                           ▼
                                     output.csv ← FINAL OUTPUT
```

## Installation
Make sure to 'cd' into this project's root folder before installation

```bash
# Create virtual environment (recommended)
python -m venv .venv311
.venv311\\Scripts\\activate.bat  # Windows
#or: source .venv311/bin/activate  # Linux/Mac

# Install dependencies
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements/requirements.lock
```

### Requirements

```
google-api-python-client
google-auth
google-auth-httplib2
google-auth-oauthlib
pillow
exifread
```

## Setup

1. **Create service account** at [Google Cloud Console](https://console.cloud.google.com/)
2. **Download credentials** and save as `secrets/inf191a-uci-nature-sa.json`
3. **Share Drive folder** with the service account email
4. **Update `FOLDER_ID`** in `scripts/config.py` if needed

## Usage

### Run Full Pipeline

```bash
python scripts/pipeline/run_pipeline.py
```
*Try 'python3' if your python version is different.

This runs all steps in order:

1. Index Drive files
2. Download images
3. Create manifest
4. Extract EXIF metadata (timestamps needed for burst grouping)
5. Run SpeciesNet (ML classification)
6. Postprocess SpeciesNet (burst voting)
7. Parse ML results
8. Extract metadata again (merge ML results into metadata.csv)
9. Generate final output CSVs (per camera, saved to `data/outputs/by_location/`)

### Upload Results to Google Drive

To also upload the output CSVs to the Google Drive database at the end of the pipeline, add ` --upload`:

```bash
python scripts/pipeline/run_pipeline.py --upload
```

This appends new rows to the existing Drive CSVs (duplicates are skipped automatically). *Add ` --overwrite` to rewrite the entire uploaded CSV to match your local version.

> **Note:** `--upload` writes directly to the production Google Drive shared with Julie. Omit it during testing.

### Run Individual Steps

```bash
# Step 1: Index Google Drive
python scripts/pipeline/build_index.py

# Step 2: Download images
python scripts/pipeline/download_drive.py

# Step 3: Create local manifest
python scripts/pipeline/make_manifest.py

# Step 4: Extract EXIF metadata 
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv

# Step 5: Run SpeciesNet ML model
python scripts/ml/run_speciesnet.py

# Step 6: Postprocess SpeciesNet (burst grouping + voting)
python scripts/ml/postprocess_speciesnet.py

# Step 7: Parse ML results into per-image CSV
python scripts/ml/run_inference.py --provider speciesnet

# Step 8: Extract metadata again (merges ml_outputs.csv into metadata.csv)
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv

# Step 9: Generate per-camera output CSVs
python scripts/pipeline/make_output.py

# (Optional) Validate output
python scripts/pipeline/validate_output.py
```

## Pipeline Steps Detail

### 1. scripts/pipeline/build_index.py

- Recursively scans Google Drive folder
- Extracts file IDs, paths, and folder structure
- Parses site/camera names from folder paths
- **Output:** `data/outputs/drive_index.csv`
- **Features:** Checkpoint/resume support, retry logic

### 2. scripts/pipeline/download_drive.py

- Downloads images using file IDs from drive_index.csv
- Preserves the Drive folder structure locally and prefixes the filename with `file_id__` for tracking
- **Output:** `data/staging/` (images), `data/outputs/download_log.csv`, `data/outputs/.download_progress.csv`
- **Features:** Resume support, exponential backoff retry, parallel downloads (12-thread pool)

### 3. scripts/pipeline/make_manifest.py

- Creates inventory of downloaded files
- Links file IDs to local paths
- **Output:** `data/outputs/manifest.csv`

### 4a. scripts/ml/run_speciesnet.py

- Runs SpeciesNet (Google's CameraTrapAI) on all images in `data/staging/`
- Internally runs MegaDetector for detection, then classifies species
- Geofenced to USA / California for accuracy
- **Output:** `data/outputs/speciesnet_results.json`

### 4b. scripts/ml/postprocess_speciesnet.py

- Groups images into bursts (same camera folder, within 300 seconds)
- Applies burst voting: all images in a burst share the highest-confidence species label
- Flags low-confidence or generic predictions for human review
- **Output:** `data/outputs/speciesnet_results.csv`, `data/outputs/speciesnet_review.csv`

### 4c. scripts/ml/run_inference.py

- Converts SpeciesNet JSON into a clean per-image CSV keyed by file_id
- Maps taxonomy strings to simplified labels (e.g., `canis_latrans` → `coyote`)
- Writes ALL predictions including blanks (`has_animal=0, species=blank`) so downstream steps can filter correctly
- **Output:** `data/outputs/ml_outputs.csv`

### 5. scripts/pipeline/extract_metadata.py

- Extracts EXIF datetime and image dimensions from each local file
- Merges ML results from ml_outputs.csv (joined on file_id)
- **Output:** `data/outputs/metadata.csv`

### 6. scripts/pipeline/make_output.py

- Assembles one CSV per camera location in Julie's spreadsheet format
- Groups images into observation bursts, assigns ObservationID, BurstCount, BurstIndex
- **Excludes blank/vehicle images** — only rows with `has_animal=1` or `has_human=1` appear in the final output
- Normalizes vague species labels to "unknown"
- **Output:** `data/outputs/by_location/<CameraName>.csv` (one file per deployment)

### validate_output.py (optional, not part of run_pipeline.py)

- Checks all required columns exist in every output CSV
- Reports row counts, species distribution, and date coverage per camera
- Run manually after the pipeline to verify results before uploading

## Output Format

The final output is one CSV per camera in `data/outputs/by_location/`. Each file contains:

| Column                      | Description                                        |
| --------------------------- | -------------------------------------------------- |
| `CameraName`                | Camera/site name (parsed from Drive folder path)   |
| `DeploymentFolder`          | SD card upload folder name                         |
| `Image#`                    | Image number extracted from filename (e.g. IMG_0042) |
| `Species`                   | Simplified species label (e.g. coyote, rabbit)     |
| `# of Individuals`          | Animal count (auto-filled as 1 if species present) |
| `CorrectedSpecies`          | Left blank for human review                        |
| `Corrected# of Individuals` | Left blank for human review                        |
| `HasMultipleSpecies`        | Left blank for human review                        |
| `SecondarySpecies`          | Left blank for human review                        |
| `Secondary# of Individuals` | Left blank for human review                        |
| `Date`                      | Image date from EXIF (YYYYMMDD)                    |
| `Time`                      | Image time from EXIF (HH:MM:SS)                    |
| `CorrectedDate`             | Filled if a time offset correction was applied     |
| `CorrectedTime`             | Filled if a time offset correction was applied     |
| `ObservationID`             | Burst group ID (e.g. BoulderCreek_20230415_000001) |
| `BurstCount`                | Total images in this burst                         |
| `BurstIndex`                | This image's position within the burst             |
| `has_animal`                | 1 = animal detected, 0 = no animal                |
| `has_human`                 | 1 = human detected                                 |
| `model_certainty`           | ML confidence score (0–1)                          |
| `Notes`                     | Warnings or offset flags; left blank for human review |

## Error Handling & Logging

The pipeline generates detailed logs:

| Log File                             | Description                    |
| ------------------------------------ | ------------------------------ |
| `data/outputs/pipeline_log.txt`      | Overall pipeline execution log |
| `data/outputs/download_log.csv`      | Download status for each file  |
| `data/outputs/inference_log.txt`     | ML processing log              |
| `data/outputs/inference_errors.csv`  | ML processing errors           |
| `data/outputs/metadata_log.txt`      | Metadata extraction log        |
| `data/outputs/metadata_errors.csv`   | Metadata extraction errors     |
| `data/outputs/output_log.txt`        | Final output generation log    |
| `data/outputs/validation_report.csv` | Data validation issues         |

### Resume Support

The pipeline supports resuming interrupted runs:

- **Indexing:** Saves checkpoint every 100 files
- **Downloads:** Tracks successfully downloaded files in `data/outputs/.download_progress.csv`
- **Re-run:** Simply run the same command again to resume

### Staging Cleanup

After a successful **auto mode** run, `data/staging/` is automatically deleted to free disk space. Re-downloads on the next run are prevented by `data/outputs/.download_progress.csv` — as long as that file exists, already-fetched images are skipped.

**Manual mode** is unaffected: staging is backed up before the run and restored afterward, so your existing images are never lost.

## Project Structure

```
project/
├── scripts/
│   ├── config.py                        # Shared config (service account, folder ID, MAX_DOWNLOADS)
│   ├── pipeline/
│   │   ├── run_pipeline.py              # Run full pipeline end-to-end
│   │   ├── build_index.py               # Step 1: Index Drive → drive_index.csv
│   │   ├── download_drive.py            # Step 2: Download images → data/staging/
│   │   ├── make_manifest.py             # Step 3: Inventory local files → manifest.csv
│   │   ├── extract_metadata.py          # Step 5: EXIF + ML merge → metadata.csv
│   │   ├── make_output.py               # Step 6: Per-camera CSVs → by_location/
│   │   └── validate_output.py           # Optional: validate output CSVs
│   ├── ml/
│   │   ├── run_speciesnet.py            # Step 4a: Run SpeciesNet → speciesnet_results.json
│   │   ├── postprocess_speciesnet.py    # Step 4b: Burst voting → speciesnet_results.csv
│   │   └── run_inference.py             # Step 4c: JSON → ml_outputs.csv
│   └── drive_upload/
│       └── upload_to_drive.py           # Upload by_location/ CSVs to Julie's Drive (production)
├── data/
│   ├── staging/                         # Downloaded images (gitignored, cleared after each successful auto run)
│   └── outputs/                         # All pipeline CSVs, JSON, logs (gitignored)
│       └── by_location/                 # Final output: one CSV per camera
├── secrets/
│   └── inf191a-uci-nature-sa.json       # Service account key (gitignored)
├── requirements/
│   └── requirements.lock                # Pinned dependencies
└── README.md
```

## Configuration

Edit these values in `scripts/config.py`:

| Setting             | File                        | Default             |
| ------------------- | --------------------------- | ------------------- |
| `MAX_DOWNLOADS`     | `scripts/config.py`         | 1000                |
| `FOLDER_ID`         | `scripts/config.py`         | (UCI Nature folder) |
| `DEFAULT_THRESHOLD` | `scripts/ml/run_inference.py` | 0.5               |

`MAX_DOWNLOADS` controls both how many files are indexed (`build_index.py`) and how many are downloaded (`download_drive.py`). You only need to change this in one place.

## Testing

### Quick Test (Small Batch)

1. Set `MAX_DOWNLOADS = 20` in `scripts/config.py` (controls both indexing and downloading)
2. Run pipeline:

```bash
python scripts/pipeline/run_pipeline.py
```

3. Check output:

```bash
python scripts/pipeline/validate_output.py
```

### Validate Output

```bash
# Check final output
python scripts/pipeline/validate_output.py

# Expected output:
# [OK] All validations passed!
# Total rows across all files: X
# With species classification: Y
```

## Team

- Ghadeer Al Jufout
- Ranya A. Alkhleef
- Andy Dao Hoang
- Jadon Tapp
- Yifan Wu

## Partner

Julie Ellen Coffey - UCI Campus Reserves Manager

## Troubleshooting

### Windows: "source is not recognized"

`source` is a Linux/macOS command. On Windows PowerShell, activate the venv with:

```powershell
.\.venv311\Scripts\Activate.ps1
```

If you see a script execution error, run this once first:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### Windows: "python3.11 is not recognized"

Windows does not ship a `python3.11` alias. Use `python` instead:

```powershell
python -m uvicorn ui.backend.main:app --reload --host 127.0.0.1 --port 8000
```

### "No module named 'uvicorn'" or "No module named 'fastapi'"

These packages are not included in `requirements.txt`. Install them manually inside the activated venv:

```powershell
pip install uvicorn fastapi python-multipart
```

### "RuntimeError: Directory 'data/staging' does not exist"

The backend mounts `data/staging` as a static file directory on startup. Create the required folders from the project root before starting the backend:

```powershell
# Windows
mkdir data\staging
mkdir data\local_input
mkdir data\outputs\by_location
```

```bash
# macOS / Linux
mkdir -p data/staging data/local_input data/outputs/by_location
```

### "No module named 'google.oauth2'"

You're running outside the virtual environment or missing the Google Drive client libraries.

Fix:

```bash
source .venv311/bin/activate
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### "No module named 'speciesnet'"

SpeciesNet is not installed in your environment.

Fix:

```bash
source .venv311/bin/activate
pip install speciesnet --use-pep517
```

### "drive_index.csv not found"

Run `python scripts/pipeline/build_index.py` first.

### "manifest.csv not found"

Run `python scripts/pipeline/download_drive.py` and `python scripts/pipeline/make_manifest.py`.

### ML columns are empty / final output has no rows

Two possible causes:
1. SpeciesNet hasn't been run yet — run `python scripts/ml/run_speciesnet.py` first.
2. All images were classified as blank (no animals detected above the 0.5 confidence threshold) — the final output CSVs will be empty because blank images are excluded. This is expected behavior if the images genuinely contain no wildlife.

### API quota errors

The pipeline uses exponential backoff. If errors persist, wait and retry.

### Downloads failing

Check `data/outputs/download_log.csv` for error details. Common issues:

- Service account doesn't have access to folder
- Network connectivity issues
- File was deleted from Drive
