#!/usr/bin/env bash
# =============================================================
# 部署 apps/pocket-relay（手机访问）到自托管主机（如 Mac Mini）
# 作为 iMessage 中继的备选访问路径：cloudflared 隧道 + 二维码 + 8 位密码
#
# 用法:
#   POCKET_HOST=user@192.168.1.10 \
#   POCKET_WEB_TARGET=http://localhost:3000 \
#   POCKET_RPC_SECRET=<随机密钥> \
#   ./deploy/deploy-pocket-relay.sh
# =============================================================
set -euo pipefail

HOST="${POCKET_HOST:-}"
PORT="${POCKET_PORT:-8788}"
WEB_TARGET="${POCKET_WEB_TARGET:-http://localhost:3000}"
RPC_SECRET="${POCKET_RPC_SECRET:-}"
SSH_KEY="${SSH_KEY:-.mac-relay-ssh}"
REMOTE_DIR="pocket-relay"

if [ -z "$HOST" ]; then
  echo "POCKET_HOST is required (user@host)."
  exit 1
fi
if [ -z "$RPC_SECRET" ]; then
  echo "POCKET_RPC_SECRET is required (random string; must match the API server config)."
  exit 1
fi

echo "==> Deploying pocket-relay to $HOST"
ssh -i "$SSH_KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=15 "$HOST" "mkdir -p $REMOTE_DIR && python3 --version"

echo "==> Copying source"
scp -i "$SSH_KEY" -r apps/pocket-relay/* "$HOST:$REMOTE_DIR/"

echo "==> Installing deps + run script"
ssh -i "$SSH_KEY" "$HOST" "cd $REMOTE_DIR && python3 -m pip install --user -r requirements.txt && cat > run.sh << EOF
#!/usr/bin/env bash
export POCKET_WEB_TARGET=$WEB_TARGET
export POCKET_PORT=$PORT
export POCKET_RPC_SECRET=$RPC_SECRET
export POCKET_AUTO_START_PUBLIC=true
exec python3 -m uvicorn main:app --host 0.0.0.0 --port $PORT
EOF
chmod +x run.sh"

echo "==> Starting service"
ssh -i "$SSH_KEY" "$HOST" "cd $REMOTE_DIR && nohup ./run.sh > pocket.log 2>&1 & sleep 3 && curl -s http://127.0.0.1:$PORT/health"

echo ""
echo "==> Done. Control page: http://$HOST:$PORT/_pocket"
echo "    API server env: POCKET_RELAY_URL=http://$(echo $HOST | cut -d@ -f2):$PORT"
echo "                     POCKET_RPC_SECRET=$RPC_SECRET"
