# 2.2 预部署 — 环境变量清单

## 新增(2.2,全部默认 OFF)

| 变量 | 默认 | 说明 |
|---|---|---|
| `LIVE_TRADING_ENABLED` | false | LIVE 总闸(多层门之一) |
| `LIVE_TRADING_DEPLOYMENT_APPROVED` | false | 部署标记 |
| `LIVE_TRADING_PROVIDER` | 空 | 券商标识;未配置时 gateway 拒绝 |
| `LIVE_TRADING_VENUE` | MOCK | 报价场所 |
| `LIVE_TRADING_ALLOWED_SYMBOLS` | 空 | 全局资产白名单(逗号分隔) |
| `LIVE_TRADING_GATEWAY` | mock | mock(诚实拒绝)或 nautilus |
| `LIVE_TRADING_ORDER_TIMEOUT_SECONDS` | 8 | 提交超时 → UNKNOWN,只查询 |
| `LIVE_TRADING_DEFAULT_MAX_NOTIONAL` | 1000 | 审批默认最大名义金额 |
| `LIVE_CREDENTIAL_ENCRYPTION_KEY` | 空 | 券商凭据 Fernet 密钥;缺省由 ENCRYPTION_MASTER_KEY 派生 |
| `LIVE_PRICE_REFRESH_INTERVAL_SECONDS` | 10 | 行情 5–15s 预算 |
| `LIVE_BALANCE_SYNC_INTERVAL_SECONDS` | 45 | 余额/持仓 30–60s |
| `LIVE_ORDER_SYNC_INTERVAL_SECONDS` | 8 | 订单状态 5–10s |
| `LIVE_NAV_CALC_INTERVAL_SECONDS` | 45 | NAV 30–60s |
| `LIVE_NAV_PRICE_STALE_SECONDS` | 60 | 超时 NAV=null |
| `LIVE_RECONCILIATION_HOUR_UTC` | 0 | 每日对账小时 |

## 保持 false 的硬约束

- `NAUTILUS_LIVE_TRADING_ENABLED=false`
- `NAUTILUS_ALLOW_LIVE_ORDER=false`
- `NAUTILUS_ALLOW_WITHDRAWAL=false`(提现禁止)
- `NAUTILUS_ALLOW_TRANSFER=false`(转账禁止)

`validate_production_settings` 仍会拒绝任何 LIVE/提现/转账开启。

## 既有(会员等级相关,无新变量)

会员等级走 DB(`users.membership_tier`)与 admin 端点,不依赖环境变量。

完整清单:`.env.example` 与 `docs/getting-started/ENVIRONMENT_VARIABLES.md`。
