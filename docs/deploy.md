# UCI-NATURE — Run, Deploy & Smoke Test Cheat Sheet

This is the quick reference for running the plain HTML/CSS/JS UI locally and
deploying the same code to AWS behind Caddy + Docker. The frontend is **not**
React/Vite — it's static files served by nginx in production and any static
server during local dev.

---

## 1. Local development

You need two processes: the FastAPI backend on `127.0.0.1:8000` and any static
file server (or Python's built-in one) for `ui/index.html`.

```bash
# Terminal 1 — backend
cd ~/UCI-NATURE
source .venv311/bin/activate          # or your preferred venv
pip install -r requirements/requirements.txt
uvicorn ui.backend.main:app --reload --host 127.0.0.1 --port 8000

# Terminal 2 — static UI on http://127.0.0.1:5500
cd ~/UCI-NATURE/ui
python3 -m http.server 5500
# Then open http://127.0.0.1:5500/  in your browser
```

The frontend auto-detects local dev (hostname `127.0.0.1` / `localhost`) and
talks to the backend at `http://127.0.0.1:8000`. On any other hostname it
falls back to same-origin `/api`, which is what Caddy serves on AWS.

### Override the API base (optional)

Add this to the top of `<head>` in `ui/index.html` if you ever need to point
the UI at a different backend (e.g., a staging tunnel):

```html
<meta name="uci-nature-backend-base" content="https://my-tunnel.example.com">
```

---

## 2. AWS Docker deploy

The production target is `https://uci-nature-pipeline.duckdns.org`. The whole
stack is three containers managed by `docker compose` in `docker/`:

- **backend** — FastAPI on port 8000 (internal only)
- **frontend** — nginx serving `ui/` on port 80 (internal only)
- **caddy** — public ingress on ports 80/443, proxies `/api` to backend and
  everything else to nginx, terminates TLS

### Build & deploy from `~/UCI-NATURE/docker`

```bash
cd ~/UCI-NATURE/docker

# Pull latest code first
git -C ~/UCI-NATURE pull --ff-only

# Rebuild and restart everything (forces fresh frontend image with latest UI)
docker compose build --no-cache frontend
docker compose up -d --force-recreate

# Or, if only the backend changed:
docker compose build backend
docker compose up -d --force-recreate backend
```

### Useful inspection commands

```bash
docker compose ps
docker compose logs -f caddy
docker compose logs -f backend
docker compose logs -f frontend

# Confirm the new UI is actually inside the container
docker compose exec frontend sh -c 'grep UCI_NATURE_ASSET_VERSION /usr/share/nginx/html/index.html || head -20 /usr/share/nginx/html/index.html'
```

### Forcing browsers to flush stale assets

Each deploy should bump the `?v=...` query string on the asset references in
`ui/index.html` (look for `20260515-1`). The nginx and Caddy configs now also
emit `Cache-Control: no-store` for HTML responses, so users will always pull a
fresh `index.html` and pick up the new versioned URLs on next reload.

---

## 3. Backend API smoke test

Run from your dev machine (or from inside the caddy network on AWS). Replace
`BASE` to switch targets.

```bash
BASE=http://127.0.0.1:8000        # local dev
# BASE=https://uci-nature-pipeline.duckdns.org   # AWS

# 1. Health
curl -fsS "$BASE/api/health" | jq .

# 2. Local (guest) login — returns access_token
TOKEN=$(curl -fsS -X POST "$BASE/api/auth/login" \
  -H 'Content-Type: application/json' \
  -d '{"email":"","project":"uci"}' | jq -r .access_token)
echo "TOKEN=$TOKEN"

# 3. Who am I (should echo {"project":"uci"})
curl -fsS "$BASE/api/auth/me" -H "Authorization: Bearer $TOKEN" | jq .

# 4. Drive status (guest mode → connected:false, google_authenticated:false)
curl -fsS "$BASE/api/drive/status" -H "Authorization: Bearer $TOKEN" | jq .

# 5. Google OAuth start URL (only useful if google creds are configured)
curl -fsS "$BASE/api/auth/google/start" -H "Authorization: Bearer $TOKEN" | jq .

# 6. Pipeline status
curl -fsS "$BASE/api/pipeline/status" -H "Authorization: Bearer $TOKEN" | jq .

# 7. Dashboard summary
curl -fsS "$BASE/api/dashboard/summary" -H "Authorization: Bearer $TOKEN" | jq .
```

If `/api/health` fails on AWS, Caddy isn't routing `/api` correctly — check
`docker/Caddyfile` and `docker compose logs caddy`.

---

## 4. Browser smoke test checklist

Run through this after every deploy with **DevTools → Network** open and
**Disable cache** checked.

1. Visit `https://uci-nature-pipeline.duckdns.org/`.
   - **Network:** `index.html` shows `Cache-Control: no-store`.
   - **Network:** `main.js?v=...` and all `*.css?v=...` requests return 200.
   - **Console:** prints `App start` then `Markup loaded`. No red errors.
2. The boot splash disappears and the login card appears.
3. Click **Continue** → step 2 shows the "Connect Google Drive" and
   "Continue as Guest" buttons.
4. Click **Continue as Guest**.
   - **Network:** `POST /api/auth/login` returns 200 with an `access_token`.
   - You land on the Dashboard / Upload page.
5. Click **Connect Google Drive** (in another session).
   - **Network:** `POST /api/auth/login` then `GET /api/auth/google/start`
     return 200; browser redirects to `accounts.google.com`.
6. After OAuth callback you should land on the Drive confirm modal.
   Click **Confirm & Enter Dashboard**.
   - **Network:** `POST /api/drive/connect` returns 200 with `connected: true`.
7. Pick a Drive folder → click **Sync**.
   - **Network:** `POST /api/drive/sync` returns 200.
   - The Drive sync card switches to "Syncing…" and the percentage advances.
8. Navigate to **Run Model**, **Review**, **Validate**, **Export**,
   **Statistics** — each page renders without console errors.

### Common console signs to watch for

- `startGoogleSignIn is not defined` — you're on a stale `index.html`.
  Hard-reload (Cmd-Shift-R / Ctrl-F5). If it persists, check that the deployed
  `index.html` includes the inline pre-bind shim (search the page source for
  `__uciNatureFlushDeferred`).
- `Failed to load partial: …` — a feature partial 404'd. Confirm the nginx
  container actually has `ui/src/features/...` files
  (`docker compose exec frontend ls /usr/share/nginx/html/src/features`).
- `Mixed content` warnings — backend base resolved to `http://...` while the
  page loaded over HTTPS. Verify Caddy is terminating TLS and that the UI is
  using the same-origin `/api` path (default on non-localhost hostnames).
