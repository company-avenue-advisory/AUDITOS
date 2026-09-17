# Deploying AuditOS: backend on DigitalOcean, frontend on Vercel

Split deployment: the Next.js frontend deploys to Vercel (best fit for Next.js,
generous free tier); the backend, worker, beat, Postgres, and Redis run as one
Docker Compose stack on a single DigitalOcean droplet, replacing the equivalent
services in [render.yaml](../render.yaml).

Droplet: `159.65.152.27` (Ubuntu 24.04, Docker marketplace image).

## 1. Point DNS for the API

Add an A record for your API subdomain → `159.65.152.27`.
Caddy issues a Let's Encrypt cert for it automatically once DNS resolves —
no manual cert steps needed.

If you don't have a domain yet, you can use a free wildcard DNS service to
unblock testing: `159-65-152-27.nip.io` resolves straight to the droplet IP
with no setup. The domain lives in `.env` (`CADDY_DOMAIN`, see step 3), not
in the Caddyfile itself — swapping domains later is a `.env` edit, not a
repo change.

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
- `CADDY_DOMAIN` — the domain(s)/IP from step 1, comma-separated (e.g. `api.yourfirm.com, 203-0-113-1.nip.io`)

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

## 9. Continuous deployment (GitHub Actions)

Every push to `main` auto-deploys after CI passes — see the `deploy` job in
[.github/workflows/ci.yml](../.github/workflows/ci.yml). One-time setup:

1. **Generate a dedicated deploy keypair** (don't reuse a personal key —
   this one lives in GitHub's secret store and should be revocable on its
   own):
   ```bash
   ssh-keygen -t ed25519 -f deploy_key -N ""
   ```
2. **Install the public key on the droplet**:
   ```bash
   ssh root@159.65.152.27 "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys" < deploy_key.pub
   ```
3. **Add GitHub repo settings** (Settings → Secrets and variables → Actions):
   - Secret `DEPLOY_SSH_KEY` = contents of `deploy_key` (the private key)
   - Variable `DEPLOY_HOST` = `159.65.152.27`
4. Delete the local `deploy_key`/`deploy_key.pub` files once both are saved in GitHub.

**What it does on each push to `main`:** SSHes in, checks out that exact
commit, rebuilds `backend`/`worker`/`beat`, then polls for up to 60s for
the backend's healthcheck to report `healthy` and the worker to be
`running`. If either fails to come up, it automatically checks out and
rebuilds the *previously*-deployed commit instead, so a bad deploy
self-heals back to the last known-good state without anyone needing to
notice at 2am.

**Manual rollback** (if a bad deploy passes its health check but is wrong
in some other way): either
- `git revert <bad-commit> && git push` — triggers a fresh deploy of the reverted state, or
- open the Actions tab, find the last-known-good "CI" run, and click **Re-run all jobs** — redeploys that exact commit.

## Day-2 operations (things Render did for you, now yours)

- **Backups**: [scripts/backup_postgres.sh](../scripts/backup_postgres.sh) — cron it nightly (see the file's header comment for the crontab line). Configure the commented-out `rclone` line to copy dumps offsite (a droplet-only backup dies with the droplet).
- **Updates**: pushes to `main` auto-deploy (see step 9 above). Manual fallback: `git pull && docker compose -f docker-compose.prod.yml up -d --build`.
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
