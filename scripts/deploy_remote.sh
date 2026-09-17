#!/usr/bin/env bash
# Runs ON the production droplet (via SSH, see .github/workflows/ci.yml's
# "deploy" job). Checks out the target commit, rebuilds, health-checks, and
# rolls back to the previously-deployed commit if the new one doesn't come
# up healthy within ~60s.
#
# Usage: deploy_remote.sh <target-sha>
set -e
cd "${DEPLOY_DIR:-/opt/auditos}"

TARGET_SHA="$1"
PREV_SHA=$(git rev-parse HEAD)
echo "Currently deployed: $PREV_SHA"
echo "Deploying:          $TARGET_SHA"

deploy_and_check() {
  # NOTE: called as `if deploy_and_check ...; then`, which disables `set -e`
  # for everything inside it (bash quirk: errexit doesn't apply to commands
  # that are part of a compound condition). Every step that must not fail
  # silently needs its own explicit `|| return 1` — do not rely on the
  # outer `set -e` here.
  local sha="$1"
  if [ -n "$(git status --porcelain)" ]; then
    echo "Working tree is dirty before checkout — refusing to risk discarding local changes." >&2
    git status --short >&2
    return 1
  fi
  git fetch origin main || return 1
  git checkout --quiet "$sha" || return 1
  docker compose -f docker-compose.prod.yml up -d --build backend worker beat || return 1

  for i in $(seq 1 12); do
    sleep 5
    backend_status=$(docker inspect --format='{{.State.Health.Status}}' auditos-backend-1 2>/dev/null || echo "unknown")
    worker_status=$(docker inspect --format='{{.State.Status}}' auditos-worker-1 2>/dev/null || echo "unknown")
    if [ "$backend_status" = "healthy" ] && [ "$worker_status" = "running" ]; then
      return 0
    fi
  done
  return 1
}

if deploy_and_check "$TARGET_SHA"; then
  echo "Deploy succeeded: $TARGET_SHA is live and healthy."
else
  echo "Deploy failed health check — rolling back to $PREV_SHA"
  if deploy_and_check "$PREV_SHA"; then
    echo "Rollback to $PREV_SHA succeeded."
  else
    echo "Rollback ALSO failed health check — manual intervention needed." >&2
  fi
  exit 1
fi
