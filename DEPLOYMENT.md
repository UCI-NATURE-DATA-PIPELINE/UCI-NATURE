# UCI-NATURE Deployment

## Live Deployment

- Domain: `https://uci-nature-pipeline.duckdns.org`
- Stack: AWS EC2 + Docker Compose + Caddy
- Project path on server: `~/UCI-NATURE`

## Services

The deployed Compose stack has three services:

- `backend`: FastAPI app at `ui.backend.main:app`
- `frontend`: static UI served by nginx from `ui/`
- `caddy`: reverse proxy and TLS terminator

Compose definition: `docker-compose.yml`

## Where Things Live

- Repo on server: `~/UCI-NATURE`
- Frontend source: `~/UCI-NATURE/ui`
- Backend source: `~/UCI-NATURE/ui/backend`
- Pipeline code: `~/UCI-NATURE/scripts`
- Data/output volume on host: `~/UCI-NATURE/data`
- Backend runtime/session/log data on host: `~/UCI-NATURE/ui/backend/data`
- Service account file on host: `~/UCI-NATURE/secrets/inf191a-uci-nature-sa.json`
- Service account file in backend container: `/app/secrets/inf191a-uci-nature-sa.json`

## Environment and Secrets

`.env` is used by the `backend` service through `env_file` in `docker-compose.yml`.

Important runtime values currently come from:

- `UCI_NATURE_PUBLIC_FRONTEND_ORIGIN`
- `UCI_NATURE_PUBLIC_BACKEND_ORIGIN`
- `UCI_NATURE_GOOGLE_OAUTH_CLIENT_ID`
- `UCI_NATURE_GOOGLE_OAUTH_CLIENT_SECRET`
- `UCI_NATURE_GOOGLE_OAUTH_REDIRECT_URI`
- `UCI_NATURE_FRONTEND_SUCCESS_REDIRECT`
- `UCI_NATURE_OUT_DIR`
- `UCI_NATURE_PIPELINE_DRIVE_CACHE_POLICY`
- `UCI_NATURE_SERVICE_ACCOUNT_FILE`

Current Google OAuth callback URI:

- `https://uci-nature-pipeline.duckdns.org/api/auth/google/callback`

## Rebuild / Restart

From the server:

```bash
cd ~/UCI-NATURE
docker compose up -d --build
```

Targeted rebuilds:

```bash
cd ~/UCI-NATURE
docker compose up -d --build frontend
docker compose up -d --build backend
docker compose up -d --build caddy
```

Restart without rebuilding:

```bash
cd ~/UCI-NATURE
docker compose restart backend frontend caddy
```

## Check Container Status

```bash
cd ~/UCI-NATURE
docker compose ps
```

## Check Logs

Follow live logs:

```bash
cd ~/UCI-NATURE
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f caddy
```

Recent logs only:

```bash
cd ~/UCI-NATURE
docker compose logs --tail=200 backend
docker compose logs --tail=200 frontend
docker compose logs --tail=200 caddy
```

Useful on-disk logs:

- `ui/backend/data/logs/`
- `data/outputs/logs/`

## Current Run Flow

1. User opens the deployed UI.
2. Google OAuth is handled by the backend.
3. User selects a Drive folder from the picker.
4. If the picker is not enough, the user can paste a Google Drive folder URL or raw folder ID as a fallback.
5. The backend stores the selected folder in session state.
6. Drive runs stage files into `data/staging/`, then run the existing pipeline.
7. Local mode still works against already-staged files.

## Folder Selection Notes

The main folder picker is intended to support:

- My Drive folders
- shared folders
- shortcut-backed folders

The UI also includes a manual fallback input that accepts:

- a Google Drive folder URL
- a raw folder ID

That fallback uses the existing `/api/drive/select-folder` route and keeps the normal selected-folder flow unchanged.

## Troubleshooting

### Docker daemon not running

Symptoms:

- `docker compose` fails immediately
- container status commands error out

Fix:

- start Docker Desktop or the Docker daemon on the EC2 host
- rerun `docker compose ps`

### Stale frontend cache

Symptoms:

- backend changes are live but the browser still behaves like old UI code

Fix:

- hard refresh the browser
- if needed, bump the versioned `app.js` URL in `ui/index.html`
- rebuild the frontend:

```bash
cd ~/UCI-NATURE
docker compose up -d --build frontend
```

### Folder picker not showing shared or shortcut folders

Checks:

- click `Refresh Folders`
- confirm the backend is authenticated with Google
- confirm `/api/drive/folders` returns `source: "shared"` and `source: "shortcut"` rows
- add the folder to My Drive or create a shortcut, then refresh

Fallback:

- paste the folder URL or raw folder ID into the manual fallback field below the dropdown

### Manual folder URL/ID fallback

Use this when:

- the folder picker is incomplete
- the folder is easier to reach from Drive than from the dropdown

Accepted input:

- full folder URL such as `https://drive.google.com/drive/folders/...`
- raw folder ID

### Non-image files in Drive folders

Selected Drive folders may contain non-image files. That is acceptable, but pipeline processing is still image-focused and intended for camera-image inputs.
