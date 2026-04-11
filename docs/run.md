# Run

The backend Python pipeline is the main workflow. Ignore the frontend, UI, Docker, and deployment files for this docs site.

## A. Local SD card or local folder workflow

If you already copied images from an SD card onto your computer, run the pipeline in manual mode and point it at that folder.

```bash
source .venv/bin/activate
python scripts/pipeline/run_pipeline.py --mode manual --folder /absolute/path/to/images
```

This is the simplest local run path.

You can also place images under:

```text
data/staging/
```

The main outputs go to:

```text
data/outputs/
data/outputs/by_location/
```

## B. Google Drive workflow

Use this when the source images are still in Google Drive.

### Step 1: build index

Scans the Drive folder and writes the file index.

```bash
python scripts/pipeline/build_index.py
```

### Step 2: download images

Downloads indexed images into local staging.

```bash
python scripts/pipeline/download_drive.py
```

### Step 3: create manifest

Builds the manifest used by the later pipeline steps.

```bash
python scripts/pipeline/make_manifest.py
```

### Step 4: extract metadata

Reads EXIF metadata before the ML steps run.

```bash
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
```

### Step 5: run ML

Runs SpeciesNet on the staged images.

```bash
python scripts/ml/run_speciesnet.py
```

### Step 6: postprocess

Builds review-ready model results.

```bash
python scripts/ml/postprocess_speciesnet.py
```

### Step 7: generate inference CSVs

Converts model output into pipeline CSV data.

```bash
python scripts/ml/run_inference.py --provider speciesnet
```

### Step 8: merge metadata again

Writes metadata with the ML fields merged in.

```bash
python scripts/pipeline/extract_metadata.py --manifest data/outputs/manifest.csv
```

### Step 9: make output

Writes the final per-camera CSV files.

```bash
python scripts/pipeline/make_output.py
```

### Step 10: validate output

Checks the final CSV output.

```bash
python scripts/pipeline/validate_output.py
```

You can also run the Drive-based flow through the main entry point:

```bash
source .venv/bin/activate
python scripts/pipeline/run_pipeline.py --resume
```

To change which Drive folder is used, update the folder in `scripts/config.py` or pass Drive-specific arguments such as:

```bash
python scripts/pipeline/run_pipeline.py --drive_root YOUR_FOLDER_ID
python scripts/pipeline/run_pipeline.py --start_folders ID1,ID2
```

`--drive_root` sets the root folder to index. `--start_folders` lets you start from specific Drive folders.

## C. Batch run option

Runs the full pipeline automatically for a batch manifest.

```bash
./run_batch.sh batch_0001.csv
```

Batch CSV files come from:

```text
data/outputs/batches/
```

## D. Test CSV generation

Creates fake output CSVs without running ML.

```bash
python create_test_csvs.py
```

Use this when you want sample output files for testing.

## E. Output files

Check these files after a run:

| Path | What you should find |
| --- | --- |
| `data/outputs/manifest.csv` | File inventory for the current run |
| `data/outputs/metadata.csv` | EXIF metadata plus merged ML fields |
| `data/outputs/ml_outputs.csv` | Flattened inference results |
| `data/outputs/speciesnet_review.csv` | Review-oriented output from SpeciesNet post-processing |
| `data/outputs/by_location/` | Final per-camera or per-location CSV exports |

## F. Google Drive CSV upload

Final per-camera CSVs can be uploaded back to Google Drive.

- The per-camera CSVs are created in `data/outputs/by_location/`
- `scripts/drive_upload/upload_to_drive.py` uploads those results
- Set your own Drive folder IDs before uploading
