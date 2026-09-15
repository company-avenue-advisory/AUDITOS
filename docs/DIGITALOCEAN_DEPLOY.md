# Deploying AuditOS: backend on DigitalOcean, frontend on Vercel

Split deployment: the Next.js frontend deploys to Vercel (best fit for Next.js,
generous free tier); the backend, worker, beat, Postgres, and Redis run as one
Docker Compose stack on a single DigitalOcean droplet, replacing the equivalent
services in [render.yaml](../render.yaml).

Droplet: `159.65.152.27` (Ubuntu 24.04, Docker marketplace image).

## 1. Point DNS for the API

Add an A record for `api.yourfirm.example` → `159.65.152.27`.
Caddy issues a Let's Encrypt cert for it automatically once DNS resolves —
no manual cert steps needed.

If you don't have a domain yet, you can use a free wildcard DNS service to
unblock testing: `159-65-152-27.nip.io` resolves straight to the droplet IP
with no setup. Swap in a real domain later by editing the Caddyfile.

## 2. SSH in and clone the repo

```bash
ssh root@159.65.152.27
git clone <your-repo-url> /opt/auditos
cd /opt/auditos
```

## 3. Configure secrets

```bash
cp .env.prod.example .env
chmod 600 .env
mkdir -p secrets backend/data
# copy your Google Drive service account JSON to secrets/drive-service-account.json
nano .env
```

Fill in `.env`:
- `POSTGRES_PASSWORD` — `openssl rand -hex 24`
- `JWT_SECRET_KEY` — `openssl rand -hex 32`
- `ALLOWED_ORIGINS` — your Vercel URL(s), e.g. `https://auditos.vercel.app` (comma-separated if you add a custom domain later; **no wildcard** — the backend refuses to start in production with one, see [main.py](../backend/main.py))
- `GCS_BUCKET_NAME`, `GCP_CREDS_JSON`, `OPENROUTER_API_KEY`, `GROQ_API_KEY` — copy from current Render env vars
- `GOOGLE_DRIVE_FOLDER_ID` — copy from Render

Edit [Caddyfile](../Caddyfile) — replace `api.yourfirm.example` with your real domain
(or the nip.io address from step 1).

## 4. Bring the backend stack up

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml ps
```

## 5. Verify the backend

```bash
curl https://api.yourfirm.example/docs   # FastAPI's auto docs should load
docker compose -f docker-compose.prod.yml logs -f worker   # Celery picking up tasks
docker compose -f docker-compose.prod.yml logs -f beat     # scheduled Drive-sync ticks
```

## 6. Deploy the frontend to Vercel

From your local machine (or Vercel's dashboard, "Import Project"):

```bash
cd frontend
npx vercel
```

- Link it to a new Vercel project.
- Set the environment variable `NEXT_PUBLIC_API_URL=https://api.yourfirm.example` in
  Vercel's project settings (Settings → Environment Variables) — required at build
  time since Next.js bakes it into the client bundle.
- Redeploy after setting it: `npx vercel --prod`.

If you want the app gated to firm employees only, Vercel's **Password Protection**
(Pro plan, Settings → Deployment Protection) is the simplest option since CORS/JWT
alone still leaves the frontend URL itself publicly reachable.

## 7. Verify end-to-end

- Load the Vercel URL, log in, confirm it talks to the droplet's API (check
  Network tab requests go to `api.yourfirm.example`, not localhost).
- Trigger a real invoice sync and confirm it lands in Postgres + GCS the same as on Render.

## 8. Cut over

Once verified for a few days:
1. Point any client-facing bookmarks at the new Vercel URL.
2. Cancel the Render services (backend, worker, beat, redis, postgres, frontend).

## Day-2 operations (things Render did for you, now yours)

- **Backups**: [scripts/backup_postgres.sh](../scripts/backup_postgres.sh) — cron it nightly (see the file's header comment for the crontab line). Configure the commented-out `rclone` line to copy dumps offsite (a droplet-only backup dies with the droplet).
- **Updates**: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
- **OS patching**: `apt update && apt upgrade` periodically, reboot when kernel updates land.
- **Monitoring**: `docker compose -f docker-compose.prod.yml ps` / `logs`; DO's free droplet monitoring covers CPU/memory/disk alerts.

## Cost comparison

| | Render (current) | This setup |
|---|---|---|
| Backend web | ~$7-25/mo | included in droplet |
| Worker | ~$7-25/mo | included in droplet |
| Beat | ~$7-25/mo | included in droplet |
| Frontend | ~$7-25/mo | Vercel free tier |
| Redis | ~$10/mo | included in droplet |
| Postgres | ~$19/mo | included in droplet |
| **Total** | **~$60-130/mo** | **~$12-24/mo droplet (+ backups) + $0 Vercel** |
