## Docker Checks

Check that Docker is installed.

```bash
docker --version
```

Check that Docker Compose is installed.

```bash
docker compose version
```

Check that the Docker daemon is running.

```bash
docker info
```

Start Docker Desktop on macOS.

```bash
open -a Docker
```

Start Docker on Linux.

```bash
sudo systemctl start docker
```


## Local Docker Workflow

Build and run both services in the foreground.

```bash
docker compose -f docker/docker-compose.local.yml up --build
```

Build and run both services in the background.

```bash
docker compose -f docker/docker-compose.local.yml up --build -d
```

Show local containers.

```bash
docker compose -f docker/docker-compose.local.yml ps
```

Show matching Docker containers.

```bash
docker ps --filter "name=uci-nature"
```

Follow logs for both services.

```bash
docker compose -f docker/docker-compose.local.yml logs -f
```

Follow backend logs.

```bash
docker compose -f docker/docker-compose.local.yml logs -f backend
```

Follow frontend logs.

```bash
docker compose -f docker/docker-compose.local.yml logs -f frontend
```

Show the last 100 backend log lines.

```bash
docker compose -f docker/docker-compose.local.yml logs --tail=100 backend
```

Stop and remove local containers.

```bash
docker compose -f docker/docker-compose.local.yml down
```

Stop and remove local containers plus old orphan containers.

```bash
docker compose -f docker/docker-compose.local.yml down --remove-orphans
```

## Rebuild

Rebuild after Dockerfile or requirements changes.

```bash
docker compose -f docker/docker-compose.local.yml up --build -d
```

Force container recreation after rebuilding.

```bash
docker compose -f docker/docker-compose.local.yml up --build -d --force-recreate
```

Build fresh images without Docker cache.

```bash
docker compose -f docker/docker-compose.local.yml build --no-cache
```

Start the no-cache build.

```bash
docker compose -f docker/docker-compose.local.yml up -d --force-recreate
```

## Clear Local Data

Stop the app before clearing generated local data.

```bash
docker compose -f docker/docker-compose.local.yml down
```

Remove staged images and generated outputs. This does not remove `secrets/`.

```bash
rm -rf data/staging/* data/outputs/*
```

Recreate expected local data folders.

```bash
mkdir -p data/staging data/outputs ui/backend/data/logs ui/backend/data/sessions
```

Start the app again.

```bash
docker compose -f docker/docker-compose.local.yml up --build -d
```

## Backend Curl Checks

Check the backend root.

```bash
curl -i http://localhost:8000/
```

Check backend health.

```bash
curl -i http://localhost:8000/api/health
```

Check FastAPI docs.

```bash
curl -I http://localhost:8000/docs
```

## Local OAuth

Guest mode works without a `.env` file. Google OAuth needs OAuth client values in `.env` and matching localhost URLs in Google Cloud Console.

Add these authorized URLs in Google Cloud Console.

```bash
http://localhost:5500
http://localhost:8000/api/auth/google/callback
```

Start the app after `.env` is in place.

```bash
docker compose -f docker/docker-compose.local.yml up --build -d
```

## Compose Files

Local development uses backend and frontend only. It does not use Caddy.

```bash
docker compose -f docker/docker-compose.local.yml up --build
```

AWS production uses backend, frontend, and Caddy.

```bash
docker compose -f docker/docker-compose.aws.yml up --build -d
```

 Local work should use `docker/docker-compose.local.yml`; AWS deploys should use `docker/docker-compose.aws.yml`.

## Troubleshooting

If Docker is not running, start Docker Desktop and check again.

```bash
open -a Docker
docker info
```

If `docker` is not found, check your PATH.

```bash
which docker
```

If `docker` is missing on macOS, install Docker Desktop.

```bash
brew install --cask docker
open -a Docker
docker --version
docker compose version
```

If port `5500` is already in use, find the process.

```bash
lsof -nP -iTCP:5500 -sTCP:LISTEN
```

If port `8000` is already in use, find the process.

```bash
lsof -nP -iTCP:8000 -sTCP:LISTEN
```

Stop old local containers.

```bash
docker compose -f docker/docker-compose.local.yml down
```

Stop a known safe process by PID.

```bash
kill <PID>
```

If the frontend says the backend is offline, confirm the backend is running.

```bash
docker compose -f docker/docker-compose.local.yml ps
curl -i http://localhost:8000/api/health
```

Read backend startup logs.

```bash
docker compose -f docker/docker-compose.local.yml logs --tail=100 backend
```

Restart the local stack.

```bash
docker compose -f docker/docker-compose.local.yml down
docker compose -f docker/docker-compose.local.yml up --build -d
```

If OAuth fails locally, confirm the Google Cloud Console redirect URI exactly matches this URL.

```bash
http://localhost:8000/api/auth/google/callback
```

## AWS Deploy

SSH to the AWS host. Replace `<AWS_HOST>` with the real host name or IP.

```bash
ssh -i secrets/uci-nature-key.pem ubuntu@<AWS_HOST>
```

Go to the UCI-NATURE repo on the server.

```bash
cd ~/UCI-NATURE
```

Pull the latest changes.

```bash
git pull --ff-only
```

Deploy the AWS stack with Caddy.

```bash
docker compose -f docker/docker-compose.aws.yml up --build -d
```

Check AWS containers.

```bash
docker compose -f docker/docker-compose.aws.yml ps
```

Follow Caddy logs.

```bash
docker compose -f docker/docker-compose.aws.yml logs -f caddy
```

Follow backend logs.

```bash
docker compose -f docker/docker-compose.aws.yml logs -f backend
```

Follow frontend logs.

```bash
docker compose -f docker/docker-compose.aws.yml logs -f frontend
```

Check the deployed health endpoint.

```bash
curl -i https://uci-nature-pipeline.duckdns.org/api/health
```

Force recreate AWS containers after a rebuild.

```bash
docker compose -f docker/docker-compose.aws.yml up --build -d --force-recreate
```

Stop the AWS stack.

```bash
docker compose -f docker/docker-compose.aws.yml down
```

## Docker Note

Docker is the recommended setup because it installs backend dependencies and runs both frontend and backend with one command.

Manual local run is still possible for development, but it requires installing the Python backend dependencies yourself and running the frontend and backend separately. Use Docker when you want the fastest local setup.
