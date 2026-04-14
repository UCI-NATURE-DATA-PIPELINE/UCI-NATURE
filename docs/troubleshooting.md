# Troubleshooting

## `pip` not found

```bash
python3 -m pip install -r requirements/requirements.txt
```

## Venv not activating

Create a fresh virtual environment and activate it.

```bash
python3.11 -m venv .venv311
source .venv311/bin/activate
```

## Wrong Python version

Use Python 3.11.

```bash
python3 --version
python3.11 --version
```

## Missing dependencies

Install the project requirements from the repository root.

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements/requirements.txt
```

If the project depends on the locked environment, use:

```bash
python -m pip install -r requirements/requirements.lock
```

## `ModuleNotFoundError: No module named 'PIL'`

`PIL` comes from Pillow.

```bash
python -m pip install pillow
```

Or reinstall the project requirements:

```bash
python -m pip install -r requirements/requirements.txt
```

## `ModuleNotFoundError: No module named 'google'`

This usually means the Google auth packages are missing.

```bash
python -m pip install google-auth google-api-python-client
```

Or reinstall the project requirements:

```bash
python -m pip install -r requirements/requirements.txt
```

## Script path issues

Run commands from the repository root:

```bash
cd "/Users/yourname/Desktop/UCI-NATURE"
```

## `Folder does not exist: /absolute/path/to/images`

This means the example placeholder path was used literally. Replace it with a real local folder path.

Example:

```bash
python scripts/pipeline/run_pipeline.py --mode manual --folder "/Users/yourname/path/to/images"
```

You can drag the folder from Finder into Terminal to paste the full path.

## `SameFileError` when using manual mode

Do not point manual mode at `data/staging`. Manual mode copies files into `data/staging`, so using staging as the source causes the script to copy a file onto itself.

Wrong:

```bash
python scripts/pipeline/run_pipeline.py --mode manual --folder "/Users/.../data/staging"
```

Use a separate input folder instead:

```bash
python scripts/pipeline/run_pipeline.py --mode manual --folder "/Users/.../data/local_input"
```

## Pipeline runs but processes `0` images

Check whether the input folder is empty.

For local/manual mode:

```bash
find data/local_input -type f | head
find data/local_input -type f | wc -l
```

For Drive mode:

```bash
find data/staging -type f | head
find data/staging -type f | wc -l
```

If no images are listed, the pipeline has nothing to process.

## `download_images.py` not found

Use the actual Drive download script instead:

```bash
python scripts/pipeline/download_drive.py --index data/outputs/drive_index.csv
```

Or just run the full pipeline entry point:

```bash
python scripts/pipeline/run_pipeline.py
```

## Drive permissions or service account issues

- Check `secrets/inf191a-uci-nature-sa.json`
- Check `UCI_NATURE_SERVICE_ACCOUNT_FILE` if you changed the path
- Make sure the Drive folder is shared with the service account
- Re-run `python scripts/pipeline/build_index.py` after confirming access

## `zsh: no matches found`

This happens when trying to remove files with a wildcard in an empty folder.

Example:

```bash
rm -rf data/staging/*
```

If the folder is already empty, zsh may show:

```text
zsh: no matches found
```

This is usually harmless. You can continue.

## Pipeline runs but no CSV output appears

Check the main output files:

```bash
ls data/outputs
ls data/outputs/by_location
```

Also check:

- `data/outputs/manifest.csv`
- `data/outputs/metadata.csv`
- `data/outputs/ml_outputs.csv`
- `data/outputs/by_location/`

You can also re-run the output generation step:

```bash
python scripts/pipeline/make_output.py --manifest data/outputs/manifest.csv --metadata data/outputs/metadata.csv --drive_index data/outputs/drive_index.csv --out_dir data/outputs/by_location --burst_seconds 300 --burst_export all
```

## Pipeline finishes but `data/staging` is empty

That can be normal. The pipeline may clear `data/staging` after a successful run while keeping outputs in:

```text
data/outputs/
data/outputs/by_location/
```

## SpeciesNet is taking a long time

That is normal for larger image sets or slower hardware. Watch the progress bars and wait for the run to finish before assuming it is stuck.

## Pipeline fails mid-run

- Check the last script that failed
- Re-run that step from the repository root
- Inspect files in `data/outputs/`
- Check `data/outputs/logs/ml_summary.json` and `data/outputs/logs/unmatched_predictions.csv`

Useful checks:

```bash
ls data/outputs
cat data/outputs/logs/ml_summary.json
```

## Check outputs after a successful run

```bash
ls data/outputs
ls data/outputs/by_location
cat data/outputs/logs/ml_summary.json
```

To preview the first few rows of the final CSVs:

```bash
head -n 5 data/outputs/by_location/*.csv
```

## Batch run issues

- Make sure the batch CSV exists in `data/outputs/batches/`
- Check the filename passed to `./run_batch.sh`
- Make sure the virtual environment is available before running the script

Example:

```bash
./run_batch.sh batch_0001.csv
```
