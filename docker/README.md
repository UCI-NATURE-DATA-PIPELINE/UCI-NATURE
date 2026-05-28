# UCI-NATURE Docker Guide

Start the local app.

```bash
docker compose -f docker/docker-compose.local.yml up --build
```


Open the local frontend.

```bash
open http://localhost:5500
```


```bash
open http://localhost:8000
```

## Notes

Make sure Git and Docker Desktop are installed first.

Open Windows PowerShell and run:

```powershell
cd $env:USERPROFILE\Desktop
git clone https://github.com/UCI-NATURE-DATA-PIPELINE/UCI-NATURE.git
cd UCI-NATURE
docker compose -f docker/docker-compose.local.yml up --build
```






















