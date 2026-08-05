#!/bin/sh
set -e
cd /opt/puregamma-staging
for f in p09_e2e.py p09_e2e_a6.py p09_e2e_backtest.py; do
  docker cp "/tmp/$f" "pgstaging-api-1:/tmp/$f"
done
echo "=== clean previous evidence ==="
docker exec pgstaging-api-1 rm -f /var/lib/puregamma/backtests/p09_evidence.json
echo "=== part 1: research runner (A1-A5) ==="
docker exec pgstaging-api-1 python /tmp/p09_e2e.py
echo "=== A6: queued cancel (worker stopped) ==="
docker compose -p pgstaging -f deploy/staging/docker-compose.staging.yml stop worker
docker exec pgstaging-api-1 python /tmp/p09_e2e_a6.py create
docker compose -p pgstaging -f deploy/staging/docker-compose.staging.yml start worker
sleep 5
docker exec pgstaging-api-1 python /tmp/p09_e2e_a6.py verify
echo "=== part 2: backtests + user flow (B/C/D) ==="
docker exec pgstaging-api-1 python /tmp/p09_e2e_backtest.py
echo "=== leftover research containers (expect none) ==="
docker ps -a --filter name=puregamma-research --format '{{.Names}} {{.Status}}'
echo "ALL_E2E_DONE"
