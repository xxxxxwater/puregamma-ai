# LIVE Trading — API 文档

所有端点要求登录(JWT)。金额一律以**字符串**传输(Decimal),防止浮点。
LIVE 订单必须经过服务端授权,移动端/Web 不允许直连交易所。

## Trading

### GET /api/trading/connections
列出当前用户的券商连接(**永不返回任何密钥字段**,仅 `has_credentials` 布尔)。

### POST /api/trading/connections/test
```json
{ "connection_id": "..." }
```
仅健康检查,不回显凭据。

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
| `GET /admin/trading/reconciliations` | 查看对账记录 |

## 错误码

| HTTP | 含义 |
| --- | --- |
| 400 `ORDER_REJECTED` | 风控拒绝(附 checks 明细) |
| 400 | 参数/门控/确认短语错误 |
| 404 | 对象不存在或不属于当前用户 |
| 503 | Gateway 不可用 |
