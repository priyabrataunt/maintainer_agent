#!/usr/bin/env bash
# Full-stack browser test. Needs: Postgres running + migrated, redis-server, Chromium, built UI.
set -uo pipefail
cd "$(dirname "$0")/../.."          # repo root
export PYTHONPATH="$PWD" JWT_SECRET="e2e-secret-e2e-secret-e2e-secret-1234" GITHUB_TOKEN=e2e \
  EMBEDDING_PROVIDER=hash RETRIEVAL_MIN_SCORE=0.1 JOB_MAX_RETRIES=1 JOB_RETRY_DELAYS_S=1 \
  REDIS_URL=redis://localhost:6379/15 BACKEND_URL=http://localhost:8000
PIDS=()
cleanup() {
  for p in "${PIDS[@]}"; do kill "$p" 2>/dev/null; done
  uv run python frontend/e2e/seed.py cleanup >/dev/null 2>&1
  redis-cli -n 15 flushdb >/dev/null 2>&1
  [ -n "${STARTED_REDIS:-}" ] && redis-cli shutdown nosave >/dev/null 2>&1
}
trap cleanup EXIT

redis-cli ping >/dev/null 2>&1 || { redis-server --daemonize yes --save "" >/dev/null; STARTED_REDIS=1; sleep 1; }
read -r JWT REPO_ID USER_ID < <(uv run python frontend/e2e/seed.py) || exit 2

uv run python frontend/e2e/serve_api.py & PIDS+=($!)
uv run python frontend/e2e/serve_worker.py >/tmp/e2e-worker.log 2>&1 & PIDS+=($!)
(cd frontend && npx next start -p 3000 >/tmp/e2e-next.log 2>&1) & PIDS+=($!)

for i in $(seq 1 60); do
  curl -sf localhost:8000/health >/dev/null && curl -sf localhost:3000/ >/dev/null && break
  sleep 1
done
curl -sf localhost:8000/health >/dev/null || { echo "backend did not start"; exit 2; }
curl -sf localhost:3000/ >/dev/null || { echo "frontend did not start"; tail /tmp/e2e-next.log; exit 2; }

(cd frontend && node e2e/run.mjs "${E2E_JWT_OVERRIDE:-$JWT}" "$REPO_ID")
