# LIVE Trading — 变更文件清单

## 迁移

- `packages/database/alembic/versions/0026_live_trading_control_plane.py`(新增)

## 数据模型

- `packages/database/models.py`
  - `TradingMandate` 扩展:重命名 `asset_allowlist_json → allowed_symbols_json`、
    `approval_state → approval_status`;新增 `environment`、`status`、
    `approved_by`、`broker_connection_id`
  - 新增:`BrokerConnection` `LiveUserApproval` `TradingKillSwitch`
    `MarketPriceSnapshot` `LiveOrderIntent` `RiskCheck` `LiveOrder` `Fill`
    `LedgerEntry` `NavSnapshot` `TradingReconciliation`
  - `TradingAuditLog` 增加 `trace_id`
  - ORM 事件:ledger/risk_checks/fills/reconciliations INSERT-only

## 新增包 `packages/live_trading/`

`__init__.py` `enums.py` `flags.py` `secret_store.py` `audit.py`
`price_feed.py` `risk_engine.py` `ledger.py` `kill_switch.py`
`gateway_adapter.py` `nav.py` `reconciliation.py` `control_plane.py`

## 配置

- `apps/api/config.py` — LIVE 全部设置(默认关闭)
- `.env.example` — LIVE 段变量

## API

- `apps/api/routers/live_trading.py`(新增:`/api/trading/*` 与 `/api/portfolio/*`)
- `apps/api/main.py` — 注册两个新路由
- `apps/api/routers/admin.py` — 追加 admin LIVE 端点(审批/Kill Switch/连接/Ledger/对账)

## 后台

- `packages/workers/tasks.py` — 5 个 LIVE 任务
- `packages/workers/scheduler.py` — 5 个定时任务

## 部署

- `docker-compose.production.yml` — LIVE 环境变量透传、api/worker/scheduler
  日志大小上限(内存上限此前已有)
- `deploy/live-trading/offsite-encrypted-backup.sh`(新增)
- `deploy/live-trading/resource-alerts.sh`(新增)

## 文档

`docs/live-trading/`:ARCHITECTURE.md、FEATURE_FLAGS.md、API.md、
ROLLBACK.md、PRODUCTION_DEPLOYMENT.md、RISK_AND_PERMISSIONS.md、
CHANGES.md、STATUS.md

## 测试

- `tests/security/test_live_trading_foundation.py`(新增,16 用例)
- `tests/security/test_migration_chain.py`(head 更新为 0026)

## 实盘开启批次(见 LIVE_LAUNCH_ARCHITECTURE.md)

### 新增/修改

- `packages/live_trading/binance_spot_gateway.py`(新增):真实 Binance 现货
  执行网关(与 runtime 测试网适配同语义;超时→UNKNOWN、业务拒单→REJECTED、
  API Key 权限硬校验、凭据按连接经 secret store 解密)
- `packages/live_trading/gateway_adapter.py`:协议方法增加
  `connection_id`/`symbol` 可选参数;`get_execution_gateway()` 支持
  `LIVE_TRADING_GATEWAY=binance`
- `packages/live_trading/control_plane.py`:payload 带 `connection_id`;
  sync/cancel 传 `connection_id`+`symbol`;`test_connection` 诚实处理
  DISABLED 与 `UNSAFE_API_PERMISSIONS` 硬拒绝(+ops 告警);新增
  `bind_connection` / `revoke_connection`(撤销即暂停绑定 Mandate);
  修复 cancel 路径缺失 mandate 关系导致的崩溃
- `packages/live_trading/risk_engine.py` / `nav.py` / `reconciliation.py`:
  传 `connection_id` 到网关
- `apps/api/routers/live_trading.py`:`POST /api/trading/connections`
  (自助绑定)、`POST /api/trading/connections/{id}/revoke`、
  `GET /api/trading/fills`
- `apps/api/config.py`:新增 `LIVE_TRADING_BINANCE_BASE_URL` /
  `LIVE_TRADING_BINANCE_RECV_WINDOW_MS`;生产校验 LIVE 开启时要求
  provider 与凭据密钥
- `packages/workers/tasks.py`:`sync_live_balances_and_positions` 接真实
  余额/持仓并写服务器行情;`refresh_live_market_prices` 优先网关 ticker
- `apps/api/routers/frontend.py`:插件 manifest 新增
  `puregamma.live-trading`(默认 disabled)
- `.env.example` / `docker-compose.production.yml`:LIVE 网关变量与透传
- `tests/security/test_live_trading_gateway.py`(新增,13 用例)

### 文档

- `docs/live-trading/LIVE_LAUNCH_RUNBOOK.md`(新增)
- `docs/live-trading/FIRST_ORDER_VERIFICATION.md`(新增)
- `docs/live-trading/STATUS.md` / `API.md` / `FEATURE_FLAGS.md` 更新
- `docs/DEPLOYMENT_CHECKLIST.md` 增补实盘章节

## 未修改(保持原状)

Agent 对话、Harness Research、Memory、Portfolio、Research、Backtest、
Signals、Playbooks、Billing/Credits、自动邮件、服务器自动化、
Android/iOS 登录认证、现有 Web、PAPER/SHADOW 逻辑、nautilus-runtime
(LIVE 仍硬禁用)、既有 Alembic 链(0015–0026)。
