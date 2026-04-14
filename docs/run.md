# Run

The backend Python pipeline is the main workflow. Ignore the frontend, UI, Docker, and deployment files for this docs page.

## A. Local SD card or local folder workflow

Use this when images were copied from an SD card or already exist in a local folder on the computer.

### Step 1: activate the environment

```bash
cd "/Users/ralkhleef/Desktop/UCI-NATURE"
source .venv311/bin/activate
```

### Step 2: create the local input folder

```bash
mkdir -p data/local_input
mkdir -p data/staging
```

Copy SD card images into:

```text
data/local_input/
```

### Step 3: clean old outputs

```bash
rm -rf data/staging/*
rm -f data/outputs/manifest.csv
rm -f data/outputs/metadata.csv
rm -f data/outputs/ml_outputs.csv
rm -f data/outputs/speciesnet_results.json
rm -f data/outputs/speciesnet_results.csv
rm -f data/outputs/speciesnet_review.csv
rm -rf data/outputs/by_location
mkdir -p data/outputs/by_location
```

### Step 4: run the pipeline in manual mode

```bash
python scripts/pipeline/run_pipeline.py --mode manual --folder "/Users/ralkhleef/Desktop/UCI-NATURE/data/local_input"
```

This is the simplest local run path.

The main outputs go to:

```text
data/outputs/
data/outputs/by_location/
```

## B. Google Drive workflow

Use this when the source images are still in Google Drive.

### Full run command

```bash
cd "/Users/ralkhleef/Desktop/UCI-NATURE"
source .venv311/bin/activate

echo "Cleaning old outputs..."
rm -f data/outputs/manifest.csv
rm -f data/outputs/metadata.csv
rm -f data/outputs/ml_outputs.csv
rm -f data/outputs/speciesnet_results.json
rm -f data/outputs/speciesnet_results.csv
rm -f data/outputs/speciesnet_review.csv
rm -f data/outputs/drive_index.csv
rm -rf data/outputs/by_location
mkdir -p data/outputs/by_location

echo "Running full Drive pipeline..."
python scripts/pipeline/run_pipeline.py
```

### Step by step command

```bash
cd "/Users/ralkhleef/Desktop/UCI-NATURE"
source .venv311/bin/activate
python scripts/pipeline/build_index.py
python scripts/pipeline/download_drive.py --index data/outputs/drive_index.csv
python scripts/pipeline/run_pipeline.py
```

### What the pipeline does internally

When the full Drive pipeline runs, it performs these steps:

1. build Drive index
2. download images into local staging
3. create the manifest
4. extract EXIF metadata
5. run SpeciesNet
6. postprocess SpeciesNet results
7. generate inference CSVs
8. merge metadata again
9. write final per-location CSV outputs

You can also run the Drive-based flow through the main entry point only:

```bash
cd "/Users/ralkhleef/Desktop/UCI-NATURE"
source .venv311/bin/activate
python scripts/pipeline/run_pipeline.py
```

## C. Testing and verification commands

Use these commands to verify that the environment, inputs, and outputs are correct.

### Check that the environment is active

```bash
which python
python --version
```

### Check required imports

```bash
python -c "from PIL import Image; print('Pillow ok')"
python -c "from google.oauth2 import service_account; print('google-auth ok')"
```

### Check that local input has images

```bash
find data/local_input -type f | head
find data/local_input -type f | wc -l
```

### Check that staging has images

```bash
find data/staging -type f | head
find data/staging -type f | wc -l
```

### Check output files were created

```bash
ls data/outputs
ls data/outputs/by_location
```

### Preview the first few rows of a result CSV

```bash
head -n 5 data/outputs/by_location/*.csv
```

### Check manifest row count

```bash
wc -l data/outputs/manifest.csv
```

### Check ML summary

```bash
cat data/outputs/logs/ml_summary.json
```

### Open the output folder

```bash
open data/outputs/by_location
```

## D. Batch run option

Runs the full pipeline automatically for a batch manifest.

```bash
./run_batch.sh batch_0001.csv
```

Batch CSV files come from:

```text
data/outputs/batches/
```

## E. Test CSV generation

Creates fake output CSVs without running ML.

```bash
python create_test_csvs.py
```

Use this when you want sample output files for testing.

## F. Output files

Check these files after a run:

| Path | What you should find |
| --- | --- |
| `data/outputs/manifest.csv` | File inventory for the current run |
| `data/outputs/metadata.csv` | EXIF metadata plus merged ML fields |
| `data/outputs/ml_outputs.csv` | Flattened inference results |
| `data/outputs/speciesnet_review.csv` | Review-oriented output from SpeciesNet post-processing |
| `data/outputs/by_location/` | Final per-camera or per-location CSV exports |
| `data/outputs/logs/ml_summary.json` | Summary counts for processed images and ML results |

## G. Notes

- Use `--mode manual --folder ...` for SD card or local folder runs.
- Use `python scripts/pipeline/run_pipeline.py` for the normal Google Drive flow.
- Do not point manual mode at `data/staging/`, because the pipeline copies files into staging and will try to copy files onto themselves.
- `python scripts/pipeline/download_images.py` is outdated in this project. Use `python scripts/pipeline/download_drive.py --index data/outputs/drive_index.csv` instead.
