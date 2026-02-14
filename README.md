# Wildlife Camera Image Processing Pipeline

Automated data pipeline for processing 100,000+ wildlife camera images from UCI Campus Reserves.

## Problem

Current workflow relies on manual review by student interns. Images accumulate faster than they can be processed, creating a backlog of 100,000+ unprocessed images. No project funding available for cloud services.

## Solution

Automated pipeline that retrieves images from Google Drive, runs MegaDetector + SpeciesNet AI to classify images and identify species, and outputs per-location CSVs ready for review.

**Key result:** MegaDetector filters out ~50-70% of blank images automatically. SpeciesNet identifies species (squirrel, raccoon, coyote, etc.) so interns don't have to.

## Pipeline Flow

```
build_index.py       → Index all Google Drive images (recursive)
download_drive.py    → Download images to local staging
make_manifest.py     → Create local file inventory
run_speciesnet.py    → AI detection + species classification (single pass)
run_inference.py     → Parse SpeciesNet JSON → ml_outputs.csv
extract_metadata.py  → Extract EXIF data + merge ML results
make_output.py       → Generate filtered per-location CSVs
```

SpeciesNet runs MegaDetector internally, so one pass handles both detection and species ID.

## Requirements

- **Python 3.11** (MegaDetector is not compatible with 3.13+)
- Virtual environment with megadetector + speciesnet packages
- Google Drive service account credentials

## Installation

```bash
# Create Python 3.11 virtual environment
python3.11 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install SpeciesNet (optional, for species classification)
pip install speciesnet --use-pep517
```

## Setup

1. Create a service account at [Google Cloud Console](https://console.cloud.google.com/)
2. Save credentials as `secrets/inf191a-uci-nature-sa.json`
3. Share the Drive folder with the service account email
4. The `FOLDER_ID` is already configured in the scripts

## Usage

**Always activate the virtual environment first:**
```bash
source .venv/bin/activate
```

**Run the full pipeline:**
```bash
python scripts/pipeline/run_pipeline.py
```

**Run individual steps:**
```bash
python scripts/pipeline/build_index.py          # Index Drive
python scripts/pipeline/download_drive.py       # Download images
python scripts/pipeline/make_manifest.py        # Create manifest
python scripts/ml/run_speciesnet.py       # Run AI detection + species
python scripts/ml/run_inference.py        # Parse ML results
python scripts/pipeline/extract_metadata.py     # Extract EXIF
python scripts/pipeline/make_output.py          # Generate CSVs
```

> `run_megadetector.py` is still in the repo as a standalone fallback if needed.

## For Windows!
```bash
**Create virtual environment**
py -m venv .venv

**Activate it**
.venv\Scripts\Activate.ps1

**Install dependencies**
pip install -r requirements.txt

**Install SpeciesNet**
pip install speciesnet --use-pep517

**Set PYTHONPATH to current directory**
$env:PYTHONPATH = (Get-Location).Path

**Run the pipeline**
py scripts\run_pipeline.py
```
> (For Julie's Lab Computer)!!

## Output

### Per-Location CSVs
```
data/outputs/by_location/
├── BonitaCanyon1.csv
├── BonitaCanyon2.csv
├── Marshtrail.csv
└── ResearchPark.csv
```

Only rows with animal or human detections are included (blanks filtered out).

| Column | Source | Description |
|--------|--------|-------------|
| CameraName | Folder structure | Camera location name |
| DeploymentFolder | Folder structure | SD card upload identifier |
| Image# | Filename | Image number (e.g., IMG_0001) |
| Species | SpeciesNet | Species label (squirrel, raccoon, etc.) |
| # of Individuals | MegaDetector | Number of detections |
| Date | EXIF metadata | Date taken (YYYYMMDD) |
| Time | EXIF metadata | Time taken (HH:MM:SS) |
| has_animal | MegaDetector | 1 = animal detected |
| model_certainty | MegaDetector | Confidence score (0.0–1.0) |
| Notes | Manual | For human review notes |

## Batch testing

Set 'MAX_IMAGES' in ```config.py``` to whatever number for batch testing. Setting to 'None' does everything. 

## Adding New Species Labels

SpeciesNet returns taxonomy strings. We map them to simple labels in `run_inference.py`:

```python
SPECIES_MAP = {
    "canis latrans": "coyote",
    "sciuridae": "squirrel",
    "procyon lotor": "raccoon",
    # add new mappings here
}
```

If a species shows as "unknown" in output, find the taxonomy term in `speciesnet_results.json` and add a mapping.

## Processing at Scale

For the full 173k+ image backlog:

1. **Process in batches** — set `MAX_DOWNLOADS` in `download_drive.py`
2. **Clean staging between runs** — pipeline prompts to delete images after each run
3. **GPU recommended** — CPU processing is slow (~75 min for 100 images). An NVIDIA GPU gives 50-100x speedup.
4. **Storage:** 300 images ≈ 550 MB. Process in batches, don't store all at once.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ModuleNotFoundError: megadetector` | Activate venv: `source .venv/bin/activate` |
| `numpy` errors | `pip install "numpy<2"` |
| Pipeline uses wrong Python version | Always run from activated `.venv` |
| `drive_index.csv` has 0 rows | Check `FOLDER_ID` and service account permissions |
| Species shows as "unknown" | Add mapping to `SPECIES_MAP` in `run_inference.py` |
| SpeciesNet not found | `pip install speciesnet --use-pep517` |

## Project Structure

```
UCI-NATURE/
├── scripts/
│   ├── build_index.py         # Index Google Drive
│   ├── download_drive.py      # Download images
│   ├── make_manifest.py       # Create file manifest
│   ├── run_megadetector.py    # Standalone MegaDetector (fallback)
│   ├── run_speciesnet.py      # Run AI detection + species (primary)
│   ├── run_speciesnet.py      # Run species classification
│   ├── run_inference.py       # Parse ML results
│   ├── extract_metadata.py    # Extract EXIF data
│   ├── make_output.py         # Generate per-location CSVs
│   ├── run_pipeline.py        # Execute full pipeline
│   ├── validate_output.py     # Validate output quality
│   ├── list_drive.py          # Test Drive connection
│   └── config.py              # Shared configuration
├── data/
│   ├── staging/               # Downloaded images (temporary)
│   └── outputs/               # CSV outputs + ML results
│       └── by_location/       # Final per-camera CSVs
├── secrets/                   # Service account key (DO NOT COMMIT)
├── notes/                     # Team research notes
├── requirements.txt
├── .gitignore
└── README.md
```

## Team

- Ghadeer Al Jufout
- Ranya A. Alkhleef
- Andy Dao Hoang
- Jadon Tapp
- Yifan Wu

## Partner

Julie Ellen Coffey — UCI Campus Reserves Manager
