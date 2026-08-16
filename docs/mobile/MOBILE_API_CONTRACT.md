# PureGamma 统一移动端 API 契约（Mobile API Contract）

> 状态：契约已冻结（v1）。**后端尚未实现下列接口**，移动端据此接入并显示"功能暂不可用"。
> 后端实现时请严格按本契约返回字段名（snake_case）。任何不兼容变更必须先更新本文件并同步 Android/iOS DTO。
>
> 本文档不替代现有接口（Agent、Reports、Portfolio、Billing 等），现有接口保持原样，本次只做新增。

## 0. 通用约定

- Base URL：`https://api.puregamma.ai`（生产必须 HTTPS）
- 认证：`Authorization: Bearer <access_token>`（移动端 Keychain/Keystore 保存，绝不进入日志与源码）
- 本地化请求头：`X-PG-Locale: zh-Hans | en`（可选）
- 错误信封（沿用现有后端格式）：
  - `{"detail": {"code": "...", "message": "..."}}` 或 `{"detail": "..."}`
  - 建议错误码：`INSUFFICIENT_CREDITS`、`QUOTA_EXCEEDED`、`PERMISSION_DENIED`、`FEATURE_DISABLED`、`MAINTENANCE`、`MANDATE_PAUSED`、`RISK_BLOCKED`、`RUN_NOT_FOUND`、`STATE_CONFLICT`
- 状态码语义（移动端映射）：
  - `401` → 会话过期，自动退出/刷新
  - `403` → 无权限（服务端判定，移动端不得本地重写）
  - `429` → 限流，读取 `Retry-After`
  - `5xx` → 服务不可用；可展示缓存但必须标注 stale
  - `404/501`（新功能接口） → 移动端显示"功能暂不可用"，不得用假数据
- 所有状态以服务端返回为准；移动端缓存只用于展示，不用于资格/额度/交易判断。

## 1. 能力发现（所有功能的总开关）

### `GET /api/mobile/capabilities`

响应：

```json
{
  "harness_research_enabled": true,
  "memory_service_enabled": true,
  "auto_trading_enabled": false,
  "paper_trading_enabled": false,
  "shadow_trading_enabled": false,
  "live_trading_enabled": false,
  "user_can_start_research": true,
  "user_can_manage_memory": true,
  "user_can_view_trading_mandates": true,
  "user_can_pause_mandates": false,
  "app_min_version": "1.4.0",
  "maintenance_message": null,
  "harness_retry_enabled": true
}
```

规则：

- 全部布尔默认 `false`；移动端每次登录后重新拉取，不持久化"可用"结论。
- `live_trading_enabled` 仅作信息展示；**移动端永远不提供 LIVE 启动入口**（无论该值为何）。
- `app_min_version`：当前版本低于该值时提示升级，但不得强制退出既有功能。
- `maintenance_message`：非空时在对应功能入口展示维护提示。
- 移动端本地 Flag 只能用于 UI 文案与隐藏入口，不能反向放行被服务端关闭的能力。

## 2. Harness 研究任务

### `POST /api/research/runs`

请求：

```json
{
  "name": "BTC 资金费率回归研究",
  "prompt": "研究近 90 天 BTC 资金费率与价格偏离的关系",
  "data_sources": ["market", "news"],
  "skill": "harness_deep_research"
}
```

`skill` 仅允许服务端白名单（当前：`harness_deep_research`）。响应 `201`：`{"run": {...ResearchRun}}`。

### `GET /api/research/runs?limit=20&offset=0`

响应：`{"runs": [...], "total": 12, "limit": 20, "offset": 0}`

### `GET /api/research/runs/{run_id}`

响应：`{"run": {...ResearchRun}}`

### `POST /api/research/runs/{run_id}/cancel`

响应：`{"run": {...ResearchRun}}`（状态改为 `canceled` 或保持当前状态 + `state_conflict` 信息）。

### `POST /api/research/runs/{run_id}/retry`

由 `harness_retry_enabled` 门控；仅允许对 `failed | canceled | timed_out` 的任务重试。响应：`{"run": {...}}`。

### `GET /api/research/runs/{run_id}/artifacts`

响应：`{"artifacts": [{"id": "...", "type": "report|json|csv", "title": "...", "url": "...", "created_at": "..."}]}`

### `GET /api/research/runs/{run_id}/evidence`

响应：`{"evidence": [...ResearchEvidence], "total": 6}`

### `GET /api/research/runs/{run_id}/events`（SSE）

事件（`event:` 字段 → `data:` JSON）：

| event | data |
|---|---|
| `run.queued` | `{"run_id": "..."}` |
| `run.state` | `{"run_id": "...", "status": "running", "updated_at": "..."}` |
| `run.progress` | `{"run_id": "...", "stage": "evidence", "progress_pct": 42}` |
| `run.evidence` | `{"run_id": "...", "evidence_count": 3}` |
| `run.completed` | `{"run_id": "...", "verified": true, "degraded": false}` |
| `run.failed` | `{"run_id": "...", "message": "..."}` |
| `run.canceled` | `{"run_id": "..."}` |

要求：

- 服务端负责长任务；客户端断线后重连（Last-Event-ID 可选），重连失败则轮询 `GET /runs/{id}`。
- **未知事件类型客户端必须忽略，不得崩溃。**
- 状态机：`queued → preparing → running → validating → completed|degraded|failed|canceled|timed_out`。

### ResearchRun 对象

```json
{
  "id": "run_01J",
  "name": "BTC 资金费率回归研究",
  "status": "completed",
  "verification": "verified",           // verified | partial | degraded | failed | incomplete
  "created_at": "2026-08-15T02:00:00Z",
  "updated_at": "2026-08-15T02:11:00Z",
  "credits_used": 3.2,
  "credits_estimate": 5.0,
  "data_sources": ["market", "news"],
  "evidence_count": 6,
  "citation_count": 8,
  "is_degraded": false,
  "error_message": null,
  "summary": "摘要（无内部 Prompt）",
  "disclaimer": "研究结论未经人工验证，不构成事实断言或投资建议"
}
```

### ResearchEvidence 对象

```json
{
  "id": "ev_01",
  "run_id": "run_01J",
  "citation_index": 1,
  "provider": "coingecko",
  "title": "...",
  "url": "https://...",
  "source_scope": "market",
  "excerpt": "…",
  "is_verified": true,
  "verification_note": null,
  "fetched_at": "2026-08-15T02:03:00Z"
}
```

## 3. Memory 接口

### `GET /api/memory/settings`

```json
{
  "settings": {
    "short_term_enabled": true,
    "mid_term_enabled": false,
    "conversation_summary_enabled": true,
    "research_memory_enabled": false,
    "portfolio_memory_enabled": false,
    "consent_required": true,
    "retention_days": 30
  }
}
```

### `PATCH /api/memory/settings`

只允许修改上述 5 个布尔开关；其他字段服务端忽略。`consent_required=true` 且当前会话未同意时，任何"开启"操作返回 `403 CONSENT_REQUIRED`，移动端弹同意对话框后再次提交（附带 `consent_granted: true`）。

### `GET /api/memory/items?scope=short_term|mid_term`

```json
{
  "items": [
    {
      "id": "m_01",
      "scope": "mid_term",
      "kind": "preference",
      "content_preview": "用户偏好研究 BTC 资金费率…",
      "status": "saved",          // saved | pending | rejected | expired | deleted
      "created_at": "...",
      "expires_at": "..."
    }
  ],
  "total": 3
}
```

> 不返回原始内部 Prompt、完整上下文和内部系统字段；`content_preview` 必须脱敏（无密钥/Token/完整卡号）。

### `GET /api/memory/proposals`

```json
{
  "proposals": [
    {
      "id": "p_01",
      "scope": "mid_term",
      "kind": "preference",
      "content_preview": "…",
      "source": "agent_conversation",
      "status": "pending",
      "created_at": "...",
      "expires_at": "..."
    }
  ]
}
```

### `POST /api/memory/proposals/{id}/approve` / `POST /api/memory/proposals/{id}/reject`

响应 `200`：`{"proposal": {...status=approved|rejected}}`

### `DELETE /api/memory/items/{id}`

响应 `200`：`{"deleted": true}`（服务端校验所有权）

### `POST /api/memory/clear`

请求：`{"scope": "all" | "short_term" | "mid_term"}`；响应 `{"cleared": 4}`。服务端校验所有权。

### `GET /api/memory/export`

响应：`{"url": "<signed download url>", "expires_at": "..."}`（服务端生成签名链接，客户端不开箱解密）。

## 4. 自动交易 Mandate（只读 + 有限管理）

> 移动端绝不具备下单能力。以下接口全部服务端鉴权 + 风控。

### `GET /api/trading/mandates`

响应：`{"mandates": [...TradingMandate]}`

### `GET /api/trading/mandates/{id}`

响应：`{"mandate": {...TradingMandate}}`

### `GET /api/trading/mandates/{id}/status`

```json
{
  "status": {
    "environment": "paper",        // off | paper | shadow | live_disabled
    "running": false,
    "paused": true,
    "blocked_by_risk": true,
    "block_reason": "daily_loss_limit",
    "last_transition_at": "...",
    "last_run_at": "..."
  }
}
```

### `GET /api/trading/mandates/{id}/risk`

```json
{
  "risk": {
    "max_notional": "100000.00000000",
    "daily_loss_limit": "5000.00000000",
    "max_leverage": "2.0",
    "max_position_size_pct": "25.0"
  }
}
```

### `POST /api/trading/mandates/{id}/pause` / `POST /api/trading/mandates/{id}/resume`

- 仅当 `user_can_pause_mandates=true` 且环境为 `paper|shadow` 时服务端接受。
- 服务端必须二次校验 Mandate、用户权限、风控与 Feature Flag。
- 移动端 `LIVE`（含 `live_disabled` 环境）不渲染 pause/resume 按钮。

### `GET /api/trading/mandates/{id}/preview`

响应：`{"preview": {"pending_orders": 0, "risk_utilization_pct": 12.5, "as_of": "..."}}`（只读快照，非下单预演）。

### TradingMandate 对象

```json
{
  "id": "m_01",
  "name": "BTC Long Gamma (Paper)",
  "strategy_name": "long_gamma_v1",
  "environment": "paper",
  "paused": true,
  "created_at": "...",
  "updated_at": "...",
  "last_run_at": "...",
  "last_run_status": "blocked",
  "risk_block_reason": "daily_loss_limit"
}
```

## 5. 推送深链（服务端 → 移动端）

推送 payload：

```json
{
  "route": "research_run",
  "run_id": "run_01J",
  "title": "研究完成",
  "body": "BTC 资金费率回归研究已完成"
}
```

支持的 `route`（新增只增不改）：`research_run`、`agent`、`portfolio`、`account`、`research`、`today`。

移动端点击 `research_run` 通知：

1. 登录态有效 → 进入 Research → 打开对应 run 详情（先 `GET /runs/{id}` 查服务端最终状态）。
2. 登录态失效 → 登录后按 `run_id` 查询并展示。

## 6. 后端实现状态（截至 2026-08-16）

| 接口 | 状态 |
|---|---|
| `GET /api/mobile/capabilities` | ✅ 已实现（`apps/api/routers/mobile.py`，按真实可用性返回；research/memory 契约端点未落地前 `user_can_start_research` / `user_can_manage_memory` 恒 false） |
| `POST/GET /api/research/runs*`（含 cancel/retry/artifacts/evidence/events） | ❌ 未实现（DB 表与 harness 包已就绪，缺 HTTP 层） |
| `GET/PATCH /api/memory/*` | ❌ 未实现（memory 包与表已就绪，缺 HTTP 层） |
| `GET /api/trading/mandates*` | ✅ 已实现（LIVE Trading Control Plane：`/api/trading/mandates`、`/api/trading/mandates/{id}`、`pause`、`resume`、`/api/trading/safety-status`） |

移动端行为：上述接口 404/501 时，对应入口显示"功能暂不可用"，不渲染可操作按钮，不使用假数据。

## 7. 移动端实现对照

| 契约 | iOS | Android |
|---|---|---|
| capabilities | `MobileCapabilitiesDTO` | `MobileCapabilitiesDto` |
| research runs | `ResearchRunsRepository` + `ResearchRunsView` | `ResearchRunsRepository` + WebView 路由 |
| memory | `MemoryRepository` + `MemoryControlsView` | WebView 路由（capability 门控） |
| mandates | `TradingMandatesRepository` + `TradingSafetyView` | WebView 路由（capability 门控） |
