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

## 未修改(保持原状)

Agent 对话、Harness Research、Memory、Portfolio、Research、Backtest、
Signals、Playbooks、Billing/Credits、自动邮件、服务器自动化、
Android/iOS 登录认证、现有 Web、PAPER/SHADOW 逻辑、既有 Alembic 链
(0015–0025)。
