# PureGamma 统一移动端 API 契约（Mobile API Contract）

> 状态：v1（§1–§5，research / memory / mandate 能力面）+ v1.1（§8，Agent 会话、实盘 NAV 与错误码，2026-10-29）。
> §1–§5 的接口**已在后端实现**（见 §6 实现状态，个别 mandate 子资源除外）；§8 描述的是 `main` 上已经上线的服务端行为，
> 由 `tests/contract/test_mobile_agent_contract.py` 对真实路由逐项断言，并把响应落成 `docs/mobile/fixtures/` 下的样例文件，
> iOS（`PureGammaTests/MobileContractFixtureTests.swift`）与 Android（`MobileContractFixtureTest.kt`）的单元测试直接解码同一份样例。
> 字段名以服务端为准（多数为 snake_case；Agent 事件与部分 Agent 错误详情为 camelCase，见 §8）。任何不兼容变更必须先更新本文件、
> 重新生成 fixture（`PG_WRITE_MOBILE_FIXTURES=1`），并同步 Android/iOS DTO。

## 0. 通用约定

- Base URL：`https://api.puregamma.ai`（生产必须 HTTPS）
- 认证：`Authorization: Bearer <access_token>`（移动端 Keychain/Keystore 保存，绝不进入日志与源码）
- 本地化请求头：`X-PG-Locale: zh-Hans | en`（可选）
- 错误信封（沿用现有后端格式，三种形态客户端都必须接受）：
  - 结构化：`{"detail": {"code": "...", "message": "...", ...附加字段}}`——`message` 可能缺失（如 `402 {"detail":{"code":"INSUFFICIENT_CREDITS"}}`），
    附加字段必须保留（如 409 `DUPLICATE_SUBMISSION` 的 `runId`）。客户端按 `code` 分支，不按 `message` 文本分支。
  - 纯字符串：`{"detail": "..."}`——字符串本身可能就是错误码（`FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED`、`CONVERSATION_BUSY`），也可能是人类可读文本（`Conversation not found`）。
  - 校验错误（422）：`{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`。
  - 完整错误码表见 §9。
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
  "app_min_version": "1.5.0",
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

## 6. 后端实现状态（截至 2026-10-29，`main`）

| 接口 | 状态 |
|---|---|
| `GET /api/mobile/capabilities` | ✅ 已实现（`apps/api/routers/mobile.py`，按真实开关返回；`app_min_version = "1.5.0"`，另返回 `membership_tier`） |
| `POST/GET /api/research/runs*`（cancel/retry/artifacts/evidence/events） | ✅ 已实现（`apps/api/routers/harness_runs.py`，受 `harness_research_enabled` 门控，默认关闭） |
| `GET/PATCH /api/memory/*`（settings/items/proposals/clear/export） | ✅ 已实现（`apps/api/routers/memory.py`，受 `memory_service_enabled` 门控，默认关闭） |
| `GET /api/trading/mandates`、`/{id}`、`POST /{id}/pause`、`/{id}/resume`、`GET /api/trading/safety-status` | ✅ 已实现（`apps/api/routers/live_trading.py`，LIVE Trading Control Plane） |
| `GET /api/trading/mandates/{id}/status`、`/risk`、`/preview` | ❌ 未实现（§4 中这三个子资源仍是规划；状态与风控字段目前包含在 mandate 对象里） |
| Agent 会话、幂等发送、事件回放（§8.1–§8.7） | ✅ 已实现（`apps/api/routers/agent.py`、`apps/api/services/agent_service.py`） |
| `GET /api/portfolio/nav`、`/nav/history`、`/positions`（§8.3） | ✅ 已实现（`apps/api/routers/live_trading.py`），旧 `GET /portfolio` 保留 |

移动端行为：接口 404/501 或 capability 关闭时，对应入口显示"功能暂不可用"，不渲染可操作按钮，不使用假数据。

## 7. 移动端实现对照

| 契约 | iOS | Android |
|---|---|---|
| capabilities | `MobileCapabilitiesDTO` | `MobileCapabilitiesDto` |
| research runs | `ResearchRunsRepository` + `ResearchRunsView` | `ResearchRunsRepository` + WebView 路由 |
| memory | `MemoryRepository` + `MemoryControlsView` | WebView 路由（capability 门控） |
| mandates | `TradingMandatesRepository` + `TradingSafetyView` | WebView 路由（capability 门控） |
| Agent 幂等发送 / 409 附着 | `ClientRequestID` + `AgentViewModel.submit` | `ClientRequestId` + `AgentSendController` |
| 错误信封（保留 code 与附加字段） | `APIErrorDetail` / `APIError.rejected` | `ApiErrorEnvelope` / `RetrofitApiException.detail` |
| SSE 事件（未知事件忽略） | `AgentSSEEvent.decode`（`.ignored`） | `AgentStreamEvent.parse`（`Ignored`） |
| 断线恢复 / 重新附着 | `AgentRunCursor` + `AgentRunFollower` | `AgentRunCursor` + `AgentRunFollower` |
| 模型菜单 / 权限模式 | `AgentModelMenu`、`AgentPermissionMode` | `AgentModelMenu`、`AgentPermissionMode` |
| 实盘 NAV | `LiveNavRepository` + `LiveNavState` | `LiveNavRepository` + `LiveNavState` |

## 8. Agent 会话与实盘 NAV（v1.1，2026-10-29）

本节每一条都有服务端契约测试（`tests/contract/test_mobile_agent_contract.py`）与样例文件（`docs/mobile/fixtures/`）。
样例是真实响应，只把每次运行都会变化的值（UUID、时间、`latencyMs`）替换成固定值；样例文件格式为
`{"request": {"method", "path"}, "status": <int>, "body": <响应 JSON>}`，SSE 样例为原始 `event:`/`data:` 文本。

时间字段一律 ISO-8601。生产库返回带偏移量（`+00:00`）的值；部分存储（以及样例）会返回不带偏移量的值，客户端必须按 UTC 解析，不能因此整条响应解码失败。

### 8.1 (a) 幂等发送 `POST /api/agent/conversations/{id}/messages`

请求（只列移动端相关字段）：

```json
{
  "content": "What moved BTC today?",
  "client_request_id": "ios-6f1c0d1e-8c1b-4bd5-9a43-2f5a1e7c9b10",
  "locale": "zh",
  "research_mode": true,
  "data_sources": ["market", "rss"],
  "model": "default"
}
```

- `client_request_id` 可选，但移动端 1.6.0 起**每次用户发起都必须带**：必须匹配 `^[A-Za-z0-9_.:-]{8,80}$`（否则 **422**，不会创建 run）。
  iOS 用 `ios-<uuid>`，Android 用 `android-<uuid>`。**用户每发起一次新问题生成一个新值；同一次发起的重试（网络失败、用户点"重试"）复用同一个值。**
- 成功：`200 text/event-stream`，帧格式见 §8.7。样例：`agent_send_stream_completed.sse`。
- 同一会话 24 小时内重复的 `client_request_id` → **409**（样例 `agent_send_duplicate_409.json`）：

```json
{"detail": {"code": "DUPLICATE_SUBMISSION", "runId": "…", "status": "running|completed|failed|canceled|interrupted|pending", "messageId": "<assistant 消息 id>", "userMessageId": "<user 消息 id>"}}
```

  客户端行为：**不报错、不重发**。删掉本地乐观插入的用户消息，按 `runId` 附着到原 run（§8.7 的回放），终态后重新拉取会话；`status` 已是终态时直接重新拉取会话。
- 其他发送错误（都不会创建 run，也不会扣费；样例见括号）：

| 状态码 | `detail.code` | 客户端行为 |
|---|---|---|
| 429 | `AGENT_DAILY_LIMIT_REACHED` / `AGENT_CONCURRENT_LIMIT_REACHED` / `AGENT_GLOBAL_CAPACITY_REACHED`（`agent_send_limit_429.json`） | 提示对应原因；并发/全局容量可稍后用**同一** `client_request_id` 重试 |
| 402 | `INSUFFICIENT_CREDITS`（`agent_send_insufficient_credits_402.json`，没有 `message`） | 提示 Credits 不足，不提供重试 |
| 400 | `AGENT_MODEL_INVALID`（`agent_send_model_invalid_400.json`） | 回退到 `default` 模型并刷新能力 |
| 403 | `AGENT_MODEL_PLAN_REQUIRED`（`agent_send_model_plan_required_403.json`） | 提示需要升级套餐，不提供重试 |
| 503 | `AGENT_MODEL_UNAVAILABLE`（`agent_send_model_unavailable_503.json`） | 提示模型暂不可用 |
| 503 | `AGENT_MODEL_PRICING_NOT_CONFIGURED`（`agent_send_model_pricing_503.json`） | 提示该模型尚未配置计价；不得显示任何价格 |
| 404 | 纯字符串 `Conversation not found` | 见 §8.4 |
| 422 | FastAPI 校验数组 | 客户端缺陷，按通用失败处理 |

### 8.2 (b) 权限模式

- `GET /api/agent/workspace-capabilities`（`agent_workspace_capabilities.json`）：`{"permission_modes": ["read-only", "workspace-write"], "default_permission_mode": "workspace-write", ...}`。
- 客户端只提供服务端列出的、且属于 `read-only | workspace-write` 的模式；**不提供 `full-access`**。
- `PATCH /api/agent/conversations/{id}` `{"permission_mode": "read-only"}` → 200，`conversation.permission_mode` 为生效值（`agent_permission_patch_200.json`）。
- `full-access` 不带 `acknowledge_full_access: true` → **400** `{"detail": "FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED"}`（纯字符串，`agent_permission_full_access_400.json`）；带了也只会存为 `workspace-write`。
- 会话有 run 正在进行 → **409** `{"detail": "CONVERSATION_BUSY"}`（`agent_permission_busy_409.json`）：提示"等待当前回答结束"，保持原选项。
- 发送接口**忽略** payload 里的 `permission_mode`，以会话上保存的值为准；客户端不要指望通过发送请求改变权限。

### 8.3 (c)(e) 实盘 NAV 与金额

- `GET /api/portfolio/nav[?account_id=]`（`portfolio_nav_200.json`）：

```json
{"nav": {"id": "…", "account_id": "…", "nav": "101234.56789012", "cash": "25000.50000000", "gross_exposure": "76234.06789012",
         "net_exposure": "-1.00000001", "realized_pnl": "0.00000000", "unrealized_pnl": "1234.56789012", "currency": "USD",
         "price_timestamp": "…", "calculated_at": "…", "is_stale": false, "calculation_version": "1.0.0", "reconciliation_status": "ok"},
 "daily_pnl": "1234.56789012", "daily_return": "0.0123456789012"}
```

- `GET /api/portfolio/nav/history?limit=` → `{"history": [<同上 nav 对象>, ...]}`（新到旧，`portfolio_nav_history_200.json`）；`GET /api/portfolio/positions` → `{"positions": [{"symbol", "quantity", "mark_price", "market_value", "price_timestamp", "stale"}]}`。
- 没有可用实盘账户（或 `account_id` 不属于本人）→ **404** `{"detail": {"code": "TRADING_ACCOUNT_NOT_FOUND", "message": "…"}}`（三个接口各有样例 `portfolio_*_no_account_404.json`）。
  客户端行为：显示"未连接实盘账户"的空状态，**不显示 0，不显示缓存的旧 NAV**。
- 金额（e）：实盘接口的金额全部是十进制字符串（`^-?\d+(\.\d+)?$`，永远不会是 `0E-8` 这样的科学计数法）；`nav` 为 `null` 表示无法定价（显示"不可用"，不是 0）；`daily_pnl`/`daily_return` 可为 `null`。
  客户端必须用十进制类型承载（iOS `Decimal` 经 `LenientDecimal` 解码字符串或数字；Android DTO 用 `String` 承载再转 `BigDecimal`），**不得经过 `Double`/`Float`**。
  旧 `GET /portfolio` 仍返回 JSON 数字（float），Credits 永远是整数。

### 8.4 (d) 已删除的会话

`GET` / `PATCH` / `DELETE /api/agent/conversations/{id}`、`GET|POST .../messages` 对已删除（或不属于本人）的会话一律 **404** `{"detail": "Conversation not found"}`（纯字符串，`agent_conversation_deleted_404.json`）。
`GET /api/agent/conversations` 不再列出它。客户端行为：从本地列表移除该会话，清空当前视图，提示"该会话已被删除"，不重试。

### 8.5 (f) 模型目录 `GET /api/agent/capabilities` → `models[]`

样例 `agent_capabilities_models.json`。每个模型：

```json
{"id": "gpt-6-sol", "display_name": "GPT-6 Sol · OpenAI", "description": "…", "provider": "openai",
 "available": false, "reason": "pricing_not_configured", "credit_cost": null, "category": "generation",
 "capabilities": {"chat": true, "...": "..."}, "estimate": null,
 "limits": {"plans": ["Max", "Enterprise"], "plan_allowed": false, "image_input": false}}
```

- `reason`：`null`（可用）| `pricing_not_configured` | `plan_required` | `unavailable`；`available == (reason == null)`。
- `estimate`：`{"min", "max", "unit": "credits", "basis": "typical_turn", "task_type"}` 或 `null`（未定价模型永远是 `null`；客户端不得自己估价）。`credit_cost` 恒为 `null`。
- `category`：`generation`（写回答）| `evaluation`（如 `jev`，只返回类型化判断，不写回答）。**`evaluation` 模型不出现在聊天模型菜单里。**
- 菜单规则（两端一致）：只有 `available && category == "generation"` 的模型可选；不可用的 `generation` 模型置灰显示，原因文案：
  `plan_required` → "需要升级套餐"，`pricing_not_configured` → "尚未配置计价"，`unavailable`/其他 → "暂不可用"。当前选中的模型变为不可选时回退到 `default`。
- 未定价模型在发送或 `POST /api/agent/quote` 时返回 **503** `AGENT_MODEL_PRICING_NOT_CONFIGURED`（§8.1）。

### 8.6 会话快照 `GET /api/agent/conversations/{id}`

样例 `agent_conversation_active_run.json`：`{"conversation": {...}, "messages": [...], "active_run_id": "…"|null, "active_run_message_id": "…"|null,
"pending_approvals": [{"toolCallId", "tool", "arguments", "expiresAt"}]}`。`active_run_id` 非空表示服务端仍在为该会话生成回答（`pending`/`running`）。

### 8.7 (g) 实时帧与事件回放

**实时 SSE**（发送接口的响应体）：每帧 `event: <type>` + `data: <JSON object>`，`data` 必带 `seq`（该 run 内从 1 开始严格递增）与 `at`（服务端时间）。已知类型：

| type | 主要字段 | 持久化 |
|---|---|---|
| `run.started` | `runId`, `messageId`, `traceId`, `model`, `creditBalance` | 是 |
| `plan.ready` | `runId`, `intent`, `assets`, `evidenceRequirements`, … | 是 |
| `tool.started` / `tool.completed` | `toolCallId`, `tool`, `arguments`（已脱敏）/ `summary`, `error`, `latencyMs` | 是 |
| `approval.required` | `toolCallId`, `tool`, `arguments`, `expiresAt`, `runId` | 是 |
| `approval.waiting` | `toolCallId`（等待审批时约每秒一次的心跳） | **否** |
| `evidence.ready` | 证据摘要（`sufficient`, `missing`, `record_count`, …） | 是 |
| `citation` | `index`, `provider`, `title`, `url`, `publishedAt`, `sourceTimestamp`, `fetchedAt` | 是 |
| `message.delta` | `messageId`, `delta` | **否** |
| `message.completed` | `messageId`, `runId`, `creditsUsed`, `creditBalance`, … —— **成功终态** | 是 |
| `run.failed` | `runId`, `messageId`, `code`, `message`, `creditBalance` —— 失败终态（已退款） | 是 |
| `run.canceled` | `runId`, `creditBalance` —— 取消终态 | 是 |

**未知类型必须忽略（不得中断流、不得报错）**；服务端会继续新增类型。

**回放** `GET /api/agent/runs/{run_id}/events?after=<lastSeq>`（样例 `agent_run_events_running.json` / `_canceled.json` / `_interrupted.json`）：

```json
{"runId": "…", "status": "running", "messageId": "…", "conversationId": "…", "lastSeq": 5, "truncated": false,
 "events": [{"seq": 2, "type": "plan.ready", "data": {"seq": 2, "at": "…", "...": "..."}}]}
```

- 只返回 `seq > after` 的持久化事件，按 `seq` 升序，每页最多 500 条；`truncated == true` 时立即用新的 `lastSeq` 继续拉。
- 因为 `message.delta`/`approval.waiting` 不持久化，`seq` 会有空洞；`lastSeq` 是已返回的最大 `seq`（无新事件时等于 `after`）。
- `status`：`pending | running`（仍在进行）或终态 `completed | failed | canceled | interrupted`。`interrupted` 没有对应的终态帧，只能从 `status` 得知。
- 别人的 run 或不存在的 run → **404** `{"detail": "Run not found"}`（`agent_run_events_not_found_404.json`）。
- 取消 `POST /api/agent/runs/{id}/cancel` → `{"id", "status"}`（`agent_run_cancel_200.json`），幂等；已结束的 run 返回其原状态。

**客户端语义（与 Web `apps/web/lib/agent-run-events.ts`、`agent-chat.tsx#observeRun` 一致）：**

1. 维护 `activeRunId` 与 `lastSeq`。`seq <= lastSeq` 的帧是重复投递，丢弃；`data.runId` 存在且不等于 `activeRunId` 的帧属于别的 run，丢弃。
2. 实时流在终态帧之前断开（网络错误或连接被关闭）时，不判定失败：显示"连接中断，正在从服务端恢复"，用回放接口从 `lastSeq` 继续，直到 `status` 为终态；网络错误只等待重试，不算失败。
3. 到达终态后重新拉取 `GET /conversations/{id}`，**以服务端保存的消息为准**覆盖本地流式内容（内容、状态、退款信息）。
4. 回到前台或重新打开会话时，如果快照里 `active_run_id` 非空，按第 2 条附着到该 run。
5. 取消只能由用户显式触发（`POST /runs/{id}/cancel`）。进入后台、切换会话只停止观察，不调用取消。
   注意：当前服务端在 SSE 连接被关闭时会把仍在进行的 run 结束为 `interrupted`（并按已用 token 结算），回放会如实显示这个状态；
   真正的"后台继续生成"需要服务端把执行与连接解耦（DSH/Harness 会话路径），不在本契约范围内。

## 9. 错误码表

| 状态码 | code（`detail.code` 或纯字符串 detail） | 接口 | 形态 | 含义 / 客户端行为 |
|---|---|---|---|---|
| 400 | `AGENT_MODEL_INVALID` | 发送、报价 | 结构化 | 模型不在目录 → 回退 `default` |
| 400 | `FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED` | PATCH 会话 | 纯字符串 | 客户端不应再发 `full-access` |
| 400 | `ORDER_REJECTED`（含 `checks`） | 实盘下单预览 | 结构化 | 移动端不下单，仅展示 |
| 401 | — | 全部 | 任意 | 会话过期，退出登录 |
| 402 | `INSUFFICIENT_CREDITS` | 发送、重新生成 | 结构化（无 message） | Credits 不足 |
| 403 | `AGENT_MODEL_PLAN_REQUIRED` | 发送、报价 | 结构化 | 需要升级套餐 |
| 403 | `CONSENT_REQUIRED` | memory 设置 | 结构化 | 弹同意对话框后重试 |
| 404 | `Conversation not found` | 会话相关全部 | 纯字符串（文本） | §8.4：移除并提示 |
| 404 | `Run not found` | 回放、取消 | 纯字符串（文本） | 停止附着，重新拉取会话 |
| 404 | `TRADING_ACCOUNT_NOT_FOUND` | NAV、历史、持仓 | 结构化 | "未连接实盘账户"空状态 |
| 409 | `DUPLICATE_SUBMISSION`（含 `runId` 等） | 发送 | 结构化 | §8.1：附着原 run |
| 409 | `CONVERSATION_BUSY` | PATCH 权限 | 纯字符串 | 等待当前回答结束 |
| 409 | `APPROVAL_NO_LONGER_PENDING` | 工具审批 | 纯字符串 | 审批已过期或已处理，刷新 |
| 422 | — | 全部 | 校验数组 | 客户端缺陷（含非法 `client_request_id`） |
| 429 | `AGENT_DAILY_LIMIT_REACHED` / `AGENT_CONCURRENT_LIMIT_REACHED` / `AGENT_GLOBAL_CAPACITY_REACHED` | 发送、重新生成 | 结构化（无 message） | §8.1 |
| 503 | `AGENT_MODEL_UNAVAILABLE` | 发送、报价 | 结构化 | 模型暂不可用 |
| 503 | `AGENT_MODEL_PRICING_NOT_CONFIGURED` | 发送、报价、`/billing/quote` | 结构化 | 尚未配置计价，不显示价格 |

`run.failed` 帧里的 `code`（不是 HTTP 错误）：`AGENT_RUN_FAILED`、`AGENT_MODEL_UNAVAILABLE`、`AGENT_MODEL_TIMEOUT`、`MODEL_NOT_CONFIGURED`、`SKILL_RUNTIME_TIMEOUT`；均已退款，显示 `message`。

## 10. 客户端版本

| 版本 | 内容 |
|---|---|
| iOS 1.5.0 (2) / Android 1.5.0 (9) | §1–§5；发送不带 `client_request_id`，"重试"会重新 POST；iOS 遇到未知 SSE 事件会中断；无回放 |
| iOS 1.6.0 (3) / Android 1.6.0 (10) | §8 全部：幂等发送与 409 附着、错误信封保留 code、未知事件忽略、终态与断线恢复、已删除会话、实盘 NAV 空状态、十进制金额、模型菜单与权限模式过滤 |

服务端 `app_min_version` 仍为 `1.5.0`：§8 的服务端行为对 1.5.0 客户端向后兼容（`client_request_id` 可选）。是否强制升级到 1.6.0 属于产品决定，未改动。
