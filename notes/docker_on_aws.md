# AWS + Docker Deployment Guide

This guide explains how to update the deployed UCI-NATURE app on AWS, rebuild Docker containers, check logs, and troubleshoot common issues.

## What is deployed

The live deployment uses:

- AWS EC2
- Docker Compose
- Caddy as the reverse proxy
- Backend container
- Frontend container

Live site:

`https://uci-nature-pipeline.duckdns.org/`

## Who can deploy

Developers can deploy updates only if they have all of the following:
- access to the GitHub repository
- access to the EC2 server through SSH
- permission to run Docker on the server
- the repo already cloned on the server
- the required .env file and secrets already set up on the server

Do not commit secrets, .env files, or private keys to GitHub.

## How to connect to the AWS server

From your local machine, connect to the EC2 instance with SSH:
``` bash 
ssh -i /path/to/your-key.pem ubuntu@YOUR_EC2_PUBLIC_IP
```
Example:
``` bash 
ssh -i secrets/uci-nature-key.pem ubuntu@18.218.xx.xx
```
Once connected, move into the project folder:

cd ~/UCI-NATURE

How to pull the latest code

Before rebuilding anything, pull the latest changes from GitHub:
``` bash 
git pull
```
If you need to deploy from a specific branch first:
``` bash 
git checkout your-branch-name
git pull
```
How to rebuild and restart Docker

To rebuild and restart the full stack:
``` bash 
docker compose up -d --build
```
To rebuild only the backend:
``` bash 
docker compose up -d --build backend
```
To rebuild only the frontend:
``` bash 
docker compose up -d --build frontend
```
To rebuild only Caddy:
``` bash 
docker compose up -d --build caddy
```
To restart containers without rebuilding:

``` bash 
docker compose restart backend frontend caddy
```
How to check container status

Use this to confirm all containers are running:

docker compose ps

You should see services like:
	•	backend
	•	frontend
	•	caddy

How to check logs

To follow logs live:
``` bash 
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f caddy
```
To show only recent logs:
``` bash 
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 caddy
```
## Important project files

Main deployment files:
	•	docker-compose.yml
	•	Dockerfile.backend
	•	Dockerfile.frontend
	•	Caddyfile

Backend code:
	•	ui/backend/main.py

Frontend code:
	•	ui/

Pipeline code:
	•	scripts/

Runtime data:
	•	data/
	•	ui/backend/data/

## Environment variables

The backend uses values from .env.

Important variables include:

UCI_NATURE_APP_ENV=cloud
UCI_NATURE_PUBLIC_FRONTEND_ORIGIN=https://uci-nature-pipeline.duckdns.org
UCI_NATURE_PUBLIC_BACKEND_ORIGIN=https://uci-nature-pipeline.duckdns.org
UCI_NATURE_GOOGLE_OAUTH_REDIRECT_URI=https://uci-nature-pipeline.duckdns.org/api/auth/google/callback
UCI_NATURE_FRONTEND_SUCCESS_REDIRECT=https://uci-nature-pipeline.duckdns.org/?google_auth=success
UCI_NATURE_GOOGLE_OAUTH_CLIENT_ID=...
UCI_NATURE_GOOGLE_OAUTH_CLIENT_SECRET=...

If Google login fails with errors like:
	•	Missing required parameter: client_id
	•	redirect_uri_mismatch

then check the .env values on the server.

Typical deploy flow

A normal deploy looks like this:
``` bash 
cd ~/UCI-NATURE
git pull
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 caddy
```
If the frontend looks outdated

Sometimes the browser keeps old JavaScript files cached.

Try:
	•	hard refresh the page
	•	rebuild the frontend
``` bash 
docker compose up -d --build frontend
```
If needed, update versioned script references in ui/index.html.

If the backend works locally but not on AWS

Check the backend logs:

docker compose logs --tail=200 backend

Common causes:
	•	missing .env variables
	•	missing Google OAuth values
	•	secrets not mounted correctly
	•	wrong redirect URI
	•	old frontend code calling outdated backend routes

## If Google OAuth fails

Error: Missing required parameter: client_id

This usually means the backend does not have the OAuth client ID loaded.

Check the .env file on AWS.

Error: redirect_uri_mismatch

Make sure the redirect URI in Google Cloud matches exactly:

https://uci-nature-pipeline.duckdns.org/api/auth/google/callback

Also make sure the backend env uses that same exact value.

If Docker is not running or you get Docker daemon errors, start Docker first.

On EC2:
``` bash 
sudo systemctl status docker
sudo systemctl start docker
```
Then retry:
``` bash 
docker compose ps
```
## How teammates can deploy

If teammates have access, they can:
	1.	SSH into EC2
	2.	go to the repo directory
	3.	pull the latest code
	4.	rebuild containers
	5.	check logs

Commands:
``` bash 
ssh -i /path/to/key.pem ubuntu@YOUR_EC2_PUBLIC_IP
cd ~/UCI-NATURE
git pull
docker compose up -d --build
docker compose ps
docker compose logs --tail=100 backend
```
## Local Docker checks

If you want to verify the deployed stack is good after a push:
``` bash 
docker compose ps
docker compose logs --tail=100 backend
docker compose logs --tail=100 frontend
docker compose logs --tail=100 caddy
```
## Troubleshooting checklist

Site not loading
	•	check docker compose ps
	•	check Caddy logs
	•	check frontend logs

API not working
	•	check backend logs
	•	verify the backend container is running
	•	verify the frontend is calling the correct /api/... routes

Google login broken
	•	check .env
	•	check redirect URI
	•	check Google Cloud OAuth config

Old UI still showing
	•	hard refresh the browser
	•	rebuild the frontend
	•	confirm the newest code was actually pulled

## final deploy check

After each deploy, test these:
	•	homepage loads
	•	backend responds
	•	Google auth starts correctly
	•	folder selection still works
	•	pipeline run still starts
	•	status and logs still update

## Notes
	•	Do not commit .env, secrets, or private keys
	•	Keep OAuth config consistent between local and AWS
	•	if local auth fails but live auth works, the local env is probably missing values
	•	always check logs after deploy

