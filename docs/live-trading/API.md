# LIVE Trading — API 文档

所有端点要求登录(JWT)。金额一律以**字符串**传输(Decimal),防止浮点。
LIVE 订单必须经过服务端授权,移动端/Web 不允许直连交易所。

## Trading

### GET /api/trading/connections
列出当前用户的券商连接(**永不返回任何密钥字段**,仅 `has_credentials` 布尔)。

### POST /api/trading/connections(自助绑定)
```json
{
  "provider": "binance_spot",
  "account_label": "main",
  "credentials": { "api_key": "...", "api_secret": "..." }
}
```
- `provider` 必须是部署配置的 `LIVE_TRADING_PROVIDER`(当前仅 `binance_spot`);
- 凭据服务端 Fernet 加密入库,**响应永不回显明文**;
- 绑定即触发健康检查 + API Key 权限硬校验(提现/转账/杠杆/合约/期权
  任一开启 → 400 拒绝,连接标记 `ERROR`/`UNSAFE_API_PERMISSIONS`);
- 每用户最多 3 个活跃连接;仅支持 production 环境。

### POST /api/trading/connections/{id}/revoke
自助撤销连接。撤销后该连接绑定的一切 LIVE Mandate 自动暂停
(`pause_reason=connection_revoked`)。

### POST /api/trading/connections/test
```json
{ "connection_id": "..." }
```
仅健康检查,不回显凭据。mock 网关诚实返回 `DISABLED`(状态
`DISCONNECTED`,不误报为错误)。

### GET /api/trading/mandates
列出当前用户的 TradingMandate。

### GET /api/trading/mandates/{id}
单个 Mandate(含 `allowed_symbols`、限额、`approval_status`、`paused` 等)。

### POST /api/trading/orders/preview
```json
{
  "mandate_id": "...",
  "symbol": "BTCUSDT",
  "side": "buy",
  "quantity": "0.5",
  "order_type": "market",
  "limit_price": null,
  "source": "user_confirmed"
}
```
`source` 允许:`user_confirmed | strategy | admin | system`。
`live_order` 被保留并拒绝;`strategy` 来源的意图**不可直接确认**。
返回 `{intent, confirmation, trace_id}`;不通过时 400
`{"code":"ORDER_REJECTED","message":...,"checks":[...]}`。

### POST /api/trading/orders/confirm
```json
{ "order_intent_id": "...", "confirmation": "CONFIRM LIVE BTCUSDT BUY ..." }
```
幂等:同一 intent 重复确认返回原订单。风控/门控失败不提交任何真实订单。

### POST /api/trading/orders/cancel
```json
{ "client_order_id": "..." }
```
Kill Switch 触发后仍允许撤单。

### GET /api/trading/orders?mandate_id=
LIVE 订单列表(PAPER 订单仍在 `/trading/orders`)。

### GET /api/trading/orders/{id}
单笔 LIVE 订单(含 `status`、`broker_order_id`、`filled_quantity`)。

### GET /api/trading/fills?order_id=
LIVE 成交流水(append-only Fill 记录,含 `broker_fill_id`、`fee`、
`executed_at`)。

### POST /api/trading/mandates/{id}/pause
```json
{ "reason": "手动暂停" }
```

### POST /api/trading/mandates/{id}/resume
```json
{ "confirmation": "RESUME <mandate_id>" }
```
恢复需要人工确认短语,并重新过全部门控;对账/Kill Switch 引起的暂停
**必须管理员处理**,用户无法自行恢复。

### GET /api/trading/safety-status
返回静态门 + 用户审批 + 每个 Mandate 的门控 + 活动 Kill Switch。

## Portfolio(NAV 仅服务器计算)

### GET /api/portfolio/nav
当前 NAV、`daily_pnl`、`daily_return`。stale 时 `nav=null`(不伪造)。

### GET /api/portfolio/nav/history?limit=100
历史快照。

### GET /api/portfolio/positions
服务器导出的持仓(数量 × 最新有效价格);无价格时 `mark_price=null`、
`stale=true`。

## Admin(仅管理员)

| 端点 | 用途 |
| --- | --- |
| `POST /admin/trading/live-approvals` | 批准/拒绝用户 LIVE 资格 |
| `POST /admin/trading/kill-switch` | 全局/用户/Mandate/连接级开关(释放必须管理员) |
| `POST /admin/trading/connections` | 创建券商连接(凭据只存密文) |
| `GET /admin/trading/ledger` | 查看 Ledger(只读) |
| `GET /admin/trading/reconciliations` | 查看对账记录（`exceptions_only`、`unreviewed_only`、`status` 过滤；含审阅信息） |
| `POST /admin/trading/reconciliations/{id}/review` | 标记已审阅（备注必填；只追加审计，不改对账、不恢复 Mandate） |
| `GET /admin/trading/kill-switches` | 启用中与已释放的 Kill Switch |
| `GET /admin/trading/live-approvals` | 用户 LIVE 资格列表 |
| `GET /admin/trading/audit` | 管理操作审计 |
| `GET/POST /admin/trading/mandate-proposals`、`…/{id}/approve`、`/reject`、`/revoke` | Mandate 提案双人审批（`LIVE_MANDATE_PROPOSALS_ENABLED`，默认关闭） |

`POST /admin/trading/kill-switch` 与 `POST /admin/trading/live-approvals` 的原因（`reason` / `notes`）均为必填并写入审计；释放不存在的开关返回 404；管理员不能批准自己的 LIVE 资格。

## 用户侧只读与核对（所有权校验，他人资源一律 404）

| 端点 | 用途 |
| --- | --- |
| `GET /api/trading/ledger?account_id=&mandate_id=&entry_type=&cursor=&limit=` | 本人 Ledger，按 `(created_at, id)` 倒序 keyset 分页，`limit` ≤ 200，`next_cursor` |
| `GET /api/trading/reconciliation?account_id=` | Ledger 推导余额（按币种）与最近一次对账 |
| `GET /api/trading/orders/{id}/sync-status` | 最近查询时间、结果（resolved / still_unknown / query_failed）与历史 |
| `POST /api/trading/orders/{id}/recheck` | 请求重新核对：只调用查询；每单限频（429 + Retry-After）；`LIVE_ORDER_RECHECK_ENABLED` 关闭时 403 |
| `GET/POST /api/trading/mandate-proposals`、`…/{id}/revoke` | 本人提案（开关关闭时 404） |

## 错误码

| HTTP | 含义 |
| --- | --- |
| 400 `ORDER_REJECTED` | 风控拒绝(附 checks 明细) |
| 400 | 参数/门控/确认短语错误 |
| 400 `Connection rejected: ...` | 自助绑定被拒(凭据不合法/密钥权限不安全/券商不可达) |
| 404 | 对象不存在或不属于当前用户 |
| 503 | Gateway 不可用 |

## 执行网关(LIVE_TRADING_GATEWAY)

| 值 | 行为 |
| --- | --- |
| `mock`(默认) | 诚实拒绝:health=`DISABLED`,提交**不会**触碰任何券商 |
| `binance` | 真实 Binance 现货执行(生产 `https://api.binance.com`,或经 `LIVE_TRADING_BINANCE_BASE_URL` 指向测试网演练);超时→UNKNOWN 只查询不重试;权限不安全密钥硬拒绝 |
| `nautilus` | 委托 Nautilus Runtime(旧运行时 LIVE 仍硬禁用,预留路径) |
