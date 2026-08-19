#!/usr/bin/env bash
# =============================================================
# Phase 5 部署脚本 (本地 → 服务器 47.245.55.228)
# 前提: 本地 HEAD=07e15a7 已推 origin/main; SSH 可用
#
# 数据安全保证 (用户数据保留):
#   - rsync 不带 --delete, 服务器独有文件不会被删
#   - .env* 全部排除, 服务器密钥/配置不被覆盖
#   - 不使用 docker compose down -v, 数据库卷原样保留
#   - 部署前自动 pg_dump 备份到 /puregamma/backup/
#   - 本批无数据库迁移 (alembic 仍跑 upgrade head 校验, 无副作用)
# =============================================================
set -euo pipefail

KEY="${PG_KEY:-$HOME/Desktop/puregamma.ai/vscode_DEEPSEEKV4_new.pem}"
HOST="47.245.55.228"
SRC="$HOME/Desktop/puregamma.ai/puregamma-ai/"
DST="root@$HOST:/puregamma/app/"
SSH_CMD="ssh -i $KEY -o ConnectTimeout=30 -o ServerAliveInterval=10 root@$HOST"
RSH="ssh -i $KEY -o ConnectTimeout=30 -o ServerAliveInterval=10"

EXCLUDES=(
  --exclude '.git'
  --exclude '.env*'
  --exclude 'node_modules'
  --exclude '.venv*'
  --exclude '__pycache__'
  --exclude '*.pyc'
  --exclude 'DerivedData'
  --exclude '*DerivedData'
  --exclude '.next*'
  --exclude 'playwright-report'
  --exclude '*.sqlite3'
  --exclude '*.db'
  --exclude '*.tsbuildinfo'
  --exclude 'storage/'
  --exclude 'backups/'
  --exclude 'releases/'
  --exclude '.gradle/'
  --exclude 'apps/android/releases/'
  --exclude 'apps/site/dist/'
  --exclude 'apps/web/test-results/'
  --exclude 'apps/web/.next/'
  --exclude '.deployed-commit'
)

echo "==> [0/6] 连通性检查"
$SSH_CMD 'hostname && cd /puregamma/app && echo "APP_DIR_OK $(pwd)"'

echo "==> [1/6] 服务器部署前备份 (compose 配置 + 数据库)"
$SSH_CMD 'set -e
  cd /puregamma/app
  TS=$(date +%Y%m%d-%H%M%S)
  mkdir -p /puregamma/backup
  cp -f docker-compose.production.yml /puregamma/backup/compose-pre-phase5-$TS.yml 2>/dev/null || true
  # 数据库备份 (服务名 postgres, 库/用户名按 compose 实际配置)
  docker compose -f docker-compose.production.yml exec -T postgres \
    pg_dump -U "${POSTGRES_USER:-puregamma}" "${POSTGRES_DB:-puregamma}" \
    > /puregamma/backup/db-pre-phase5-$TS.sql 2>/dev/null \
    || docker compose -f docker-compose.production.yml exec -T postgres \
       pg_dumpall -U "${POSTGRES_USER:-puregamma}" > /puregamma/backup/db-pre-phase5-$TS.sql
  ls -lh /puregamma/backup/ | tail -3'

echo "==> [2/6] rsync 本地 main → 服务器 (无 --delete)"
rsync -az --progress "${EXCLUDES[@]}" -e "$RSH" "$SRC" "$DST"

echo "==> [3/6] 构建镜像"
$SSH_CMD 'cd /puregamma/app && docker compose -f docker-compose.production.yml build api worker scheduler web'

echo "==> [4/6] 滚动重启服务 (不 down -v, 卷保留)"
$SSH_CMD 'cd /puregamma/app && docker compose -f docker-compose.production.yml up -d api worker scheduler web'

echo "==> [5/6] 数据库迁移校验 (无新迁移, 应输出 head=0027)"
$SSH_CMD 'cd /puregamma/app && docker compose -f docker-compose.production.yml exec -T api \
  python -m alembic upgrade head && \
  docker compose -f docker-compose.production.yml exec -T api python -m alembic current'

echo "==> [6/6] 健康检查"
sleep 8
$SSH_CMD 'curl -s http://localhost:8000/health || docker compose -f docker-compose.production.yml exec -T api curl -s http://localhost:8000/health'
curl -s -o /dev/null -w 'app.puregamma.ai -> %{http_code}\n' --max-time 15 https://app.puregamma.ai/health
curl -s -o /dev/null -w 'api.puregamma.ai -> %{http_code}\n' --max-time 15 https://api.puregamma.ai/health

echo "==> 完成: 记录部署 commit"
$SSH_CMD 'echo 07e15a7 > /puregamma/app/.deployed-commit && echo DEPLOYED=07e15a7'
