# Wildlife Camera Image Processing Pipeline

Automated data pipeline for processing 100,000+ wildlife camera images from UCI Campus Reserves.

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

```bash
# Create virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# or: .venv\Scripts\activate  # Windows

# Install dependencies
pip install -r requirements.txt
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
4. **Update `FOLDER_ID`** in `scripts/build_index.py` if needed

## Usage

### Run Full Pipeline

```bash
python scripts/run_pipeline.py
```

This runs all steps in order:

1. Index Drive files
2. Download images
3. Create manifest
4. Run inference (ML classification)
5. Extract metadata
6. Generate final output
7. Validate output

### Run Individual Steps

```bash
# Step 1: Index Google Drive
python scripts/build_index.py

# Step 2: Download images
python scripts/download_drive.py

# Step 3: Create local manifest
python scripts/make_manifest.py

# Step 4: Process ML results (requires MegaDetector output)
python scripts/run_inference.py

# Step 5: Extract EXIF metadata
python scripts/extract_metadata.py

# Step 6: Generate final CSV
python scripts/make_output.py

# Step 7: Validate output
python scripts/validate_output.py
```

## Pipeline Steps Detail

### 1. build_index.py

- Recursively scans Google Drive folder
- Extracts file IDs, paths, and folder structure
- Parses site/camera names from folder paths
- **Output:** `data/outputs/drive_index.csv`
- **Features:** Checkpoint/resume support, retry logic

### 2. download_drive.py

- Downloads images using file IDs from drive_index.csv
- Preserves the Drive folder structure locally and prefixes the filename with `file_id__` for tracking
- **Output:** `data/staging/` (images), `data/outputs/download_log.csv`, `data/outputs/.download_progress.csv`
- **Features:** Resume support, exponential backoff retry, optional parallel downloads (thread pool)

### 3. make_manifest.py

- Creates inventory of downloaded files
- Links file IDs to local paths
- **Output:** `data/outputs/manifest.csv`

### 4. run_inference.py

- Converts MegaDetector JSON output to CSV format
- Calculates animal/blank classification
- **Input:** `data/outputs/md_results.json` (from MegaDetector)
- **Output:** `data/outputs/ml_outputs.csv`
- **Note:** If MegaDetector output is missing, creates empty ML columns

### 5. extract_metadata.py

- Extracts EXIF datetime from images
- Gets image dimensions
- Merges ML classification data
- **Output:** `data/outputs/metadata.csv`

### 6. make_output.py

- Merges all data sources into final output
- Validates required columns are present
- **Output:** `data/outputs/output.csv`, `data/outputs/validation_report.csv`

### 7. validate_output.py

- Validates final output completeness
- Checks all required columns exist
- Reports data quality statistics

## Output Format

The final `output.csv` contains these columns:

| Column            | Description                           |
| ----------------- | ------------------------------------- |
| `image_id`        | Unique file ID (from Google Drive)    |
| `camera_name`     | Camera/site name (from folder path)   |
| `date`            | Image date (YYYY-MM-DD)               |
| `time`            | Image time (HH:MM:SS)                 |
| `has_animal`      | 1 = animal detected, 0 = no animal    |
| `is_blank`        | 1 = blank image, 0 = has content      |
| `species`         | Species name (placeholder for future) |
| `count`           | Number of animals detected            |
| `model_certainty` | ML confidence score (0-1)             |

## ML Integration (MegaDetector)

To populate animal/blank classification:

1. **Run MegaDetector** on downloaded images:

```bash
python scripts/ml/run_megadetector.py
```

2. **Process results:**

```bash
python scripts/run_inference.py
python scripts/extract_metadata.py
python scripts/make_output.py
```

Without MegaDetector results, ML columns will be empty but the pipeline will still work.

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
- **Downloads:** Tracks successfully downloaded files
- **Re-run:** Simply run the same command again to resume

## Project Structure

```
project/
├── scripts/
│   ├── build_index.py       # Index Drive files
│   ├── download_drive.py    # Download images
│   ├── make_manifest.py     # Create file manifest
│   ├── run_inference.py     # Process ML output
│   ├── extract_metadata.py  # Extract EXIF data
│   ├── make_output.py       # Generate final CSV
│   ├── validate_output.py   # Validate output
│   ├── run_pipeline.py      # Run full pipeline
│   └── config.py            # Configuration
├── data/
│   ├── staging/             # Downloaded images
│   └── outputs/             # CSV outputs & logs
├── secrets/
│   └── inf191a-uci-nature-sa.json  # Service account key
├── notes/                   # Development notes
├── requirements.txt
└── README.md
```

## Configuration

Edit these values in the scripts as needed:

| Setting             | File              | Default             |
| ------------------- | ----------------- | ------------------- |
| `MAX_DOWNLOADS`     | download_drive.py | None                |
| `MAX_ROWS`          | build_index.py    | 2000                |
| `FOLDER_ID`         | build_index.py    | (UCI Nature folder) |
| `DEFAULT_THRESHOLD` | run_inference.py  | 0.5                 |

## Testing

### Quick Test (Small Batch)

1. Set `MAX_DOWNLOADS = 10` in `scripts/download_drive.py`
2. Set `MAX_ROWS = 50` in `scripts/build_index.py`
3. Run pipeline:

```bash
python scripts/run_pipeline.py
```

4. Check output:

```bash
python scripts/validate_output.py
```

### Validate Output

```bash
# Check final output
python scripts/validate_output.py

# Expected output:
# ✓ All required columns present
# Total rows: X
# With ML results: Y
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

### "No module named 'google.oauth2'"

You're running `download_drive.py` in an environment missing the Google Drive client libraries.

Fix:

```bash
conda activate ucinature-md
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

### "No module named 'megadetector'"

You're running the MegaDetector step in an environment where MegaDetector isn't installed.

Fix:

```bash
conda activate ucinature-md
pip install megadetector
```

### "drive_index.csv not found"

Run `python scripts/build_index.py` first.

### "manifest.csv not found"

Run `python scripts/download_drive.py` and `python scripts/make_manifest.py`.

### ML columns are empty

MegaDetector output (`md_results.json`) is missing. Run MegaDetector on your images first.

### API quota errors

The pipeline uses exponential backoff. If errors persist, wait and retry.

### Downloads failing

Check `data/outputs/download_log.csv` for error details. Common issues:

- Service account doesn't have access to folder
- Network connectivity issues
- File was deleted from Drive
