# Troubleshooting

## `pip` not found

```bash
python3 -m pip install -r requirements.txt
```

## Venv not activating

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## Wrong Python version

Use Python 3.11.

```bash
python3 --version
```

## Missing dependencies

```bash
python3 -m pip install -r requirements.txt
```

## Script path issues

Run commands from the repository root:

```bash
cd UCI-NATURE
```

## Drive permissions or service account issues

- Check `secrets/inf191a-uci-nature-sa.json`
- Check `UCI_NATURE_SERVICE_ACCOUNT_FILE` if you changed the path
- Make sure the Drive folder is shared with the service account

## Pipeline runs but no CSV output appears

- Check `data/outputs/manifest.csv`
- Check `data/outputs/metadata.csv`
- Check `data/outputs/by_location/`
- Re-run `python scripts/pipeline/make_output.py`

## Pipeline fails mid-run

- Check the last script that failed
- Re-run that step from the repository root
- Inspect files in `data/outputs/`

## Batch run issues

- Make sure the batch CSV exists in `data/outputs/batches/`
- Check the filename passed to `./run_batch.sh`
- Make sure the virtual environment is available before running the script
