# API Gateway (中转站) — 管理员激活指南

## 激活流程

Gateway 默认部署但未启用。按以下步骤逐一激活 Provider。

### 步骤 1：生成 API Key Pepper

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

将输出填入 `.env` 的 `GATEWAY_API_KEY_PEPPER`。

### 步骤 2：添加 Provider API Key

在 `.env` 中填入你要启用的 Provider 的官方 API Key：

```bash
# DeepSeek (https://platform.deepseek.com/api_keys)
GATEWAY_DEEPSEEK_API_KEY=sk-...

# Moonshot / Kimi (https://platform.moonshot.cn)
GATEWAY_MOONSHOT_API_KEY=sk-...

# 智谱 GLM (https://open.bigmodel.cn)
GATEWAY_GLM_API_KEY=...
```

至少需要配置一个 Provider。

### 步骤 3：启用 Gateway

```bash
GATEWAY_ENABLED=true
```

### 步骤 4：重新部署 API

```bash
docker compose --env-file .env -f docker-compose.production.yml up -d --build api
```

等待 API 健康检查通过：

```bash
curl -s https://api.puregamma.ai/health
```

### 步骤 5：Bootstrap 数据库 Catalog

以 Admin 用户登录后调用：

```bash
TOKEN="$(your-admin-jwt-token)"

# 初始化 Provider 和 Model 数据（从 config/gateway/providers.yaml）
curl -X POST https://api.puregamma.ai/admin/gateway/bootstrap \
  -H "Authorization: Bearer $TOKEN"

# 查看已注册的 Provider
curl -s https://api.puregamma.ai/admin/gateway/providers \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```

### 步骤 6：启用 Provider

```bash
# 启用 DeepSeek
curl -X PUT https://api.puregamma.ai/admin/gateway/providers/deepseek \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 启用 Moonshot
curl -X PUT https://api.puregamma.ai/admin/gateway/providers/moonshot \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'

# 启用 GLM
curl -X PUT https://api.puregamma.ai/admin/gateway/providers/glm \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"enabled": true}'
```

### 步骤 7：同步 Provider 元数据

```bash
# 同步所有 Provider
curl -X POST https://api.puregamma.ai/admin/gateway/sync \
  -H "Authorization: Bearer $TOKEN"

# 或单独同步
curl -X POST https://api.puregamma.ai/admin/gateway/providers/deepseek/sync \
  -H "Authorization: Bearer $TOKEN"
```

### 步骤 8：审核并批准定价

```bash
# 查看待审批的定价
curl -s https://api.puregamma.ai/admin/gateway/prices/pending \
  -H "Authorization: Bearer $TOKEN" | python3 -m json.tool

# 批准每个 revision（替换 {revision_id}）
curl -X POST https://api.puregamma.ai/admin/gateway/prices/{revision_id}/approve \
  -H "Authorization: Bearer $TOKEN"
```

### 步骤 9：调整 Markup（可选）

```bash
# 默认 30% markup (3000 basis points)
# 查看当前 policy
curl -s https://api.puregamma.ai/admin/gateway/pricing/policy \
  -H "Authorization: Bearer $TOKEN"

# 修改 markup（例如 20% = 2000）
curl -X PUT https://api.puregamma.ai/admin/gateway/pricing/markup \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"markup_bps": 2000}'
```

### 步骤 10：验证

```bash
# 验证 models 列表
curl -s https://api.puregamma.ai/v1/models \
  -H "Authorization: Bearer sk-pg-..."

# 健康检查
curl -X POST https://api.puregamma.ai/admin/gateway/providers/healthcheck \
  -H "Authorization: Bearer $TOKEN"
```

## 快速一键激活

将上述步骤合为一个脚本 `deploy/activate-gateway.sh`：

```bash
#!/usr/bin/env bash
set -eu
TOKEN="${1:?Usage: $0 <admin-jwt-token>}"
BASE="https://api.puregamma.ai"
H="-H Authorization: Bearer $TOKEN"
H2="-H Content-Type: application/json"

echo "=== Bootstrap ==="
curl -s -X POST "$BASE/admin/gateway/bootstrap" $H | python3 -m json.tool

echo ""
echo "=== Enable Providers ==="
for p in deepseek moonshot glm; do
  curl -s -X PUT "$BASE/admin/gateway/providers/$p" $H $H2 -d '{"enabled":true}' >/dev/null
  echo "  $p enabled"
done

echo ""
echo "=== Sync ==="
curl -s -X POST "$BASE/admin/gateway/sync" $H | python3 -m json.tool

echo ""
echo "=== Approve Prices ==="
REVISIONS=$(curl -s "$BASE/admin/gateway/prices/pending" $H)
for rid in $(echo "$REVISIONS" | python3 -c "import sys,json; [print(r['id']) for r in json.load(sys.stdin)['revisions']]" 2>/dev/null); do
  curl -s -X POST "$BASE/admin/gateway/prices/$rid/approve" $H >/dev/null
  echo "  approved $rid"
done

echo ""
echo "=== Done ==="
echo "Verify: curl -s $BASE/v1/models -H 'Authorization: Bearer sk-pg-...'"
```

## 故障排除

| 问题 | 解决方案 |
|------|----------|
| `GATEWAY_MODEL_NOT_AVAILABLE` | 确认已 bootstrap、sync、approve 定价 |
| `GATEWAY_PROVIDER_DISABLED` | `PUT /admin/gateway/providers/{name}` 设置 `enabled: true` |
| `GATEWAY_PRICING_NOT_APPROVED` | 后台审批 pending 定价 revision |
| 健康检查 unhealthy | 检查 Provider API Key 是否正确，base URL 是否可达 |
| API 返回 404 | 确认 `GATEWAY_ENABLED=true` 并已重新部署 |
