# Setup

Use Python 3.11 for this project.

## Clone the repo

```bash
git clone https://github.com/ralkhleef/UCI-NATURE.git
cd UCI-NATURE
```

## Create a virtual environment

```bash
python3 -m venv .venv
```

## Activate the environment

=== "macOS / Linux"

    ```bash
    source .venv/bin/activate
    ```

=== "Windows PowerShell"

    ```powershell
    .\.venv\Scripts\Activate.ps1
    ```

## Install dependencies

```bash
python3 -m pip install -r requirements.txt
```

## Install MkDocs

```bash
python3 -m pip install mkdocs mkdocs-material
```

## Check Python

```bash
python3 --version
```

## Drive mode only

If you want to pull images from Google Drive, keep the service account file in:

```text
secrets/inf191a-uci-nature-sa.json
```

You can also set the path with `UCI_NATURE_SERVICE_ACCOUNT_FILE`.
