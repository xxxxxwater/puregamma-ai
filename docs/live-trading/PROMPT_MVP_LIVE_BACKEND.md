# 提示词(MVP/后端工程师)— PureGamma 实盘 LIVE 开启与部署

把下面整段作为任务提示词发给 MVP/后端工程师:

---

你是 PureGamma AI 的 MVP/后端工程师。仓库中 LIVE Trading Control Plane
代码已交付但全部默认关闭(状态恒为 `LIVE_DISABLED`,所有 mock 诚实
返回)。你的任务是:**把真实现货执行链路接通,按门控顺序把实盘开启给
通过审批的用户使用,并完成部署**。

## 必读(动手前全部读完)

- `docs/live-trading/ARCHITECTURE.md`、`STATUS.md`、`FEATURE_FLAGS.md`、
  `ROLLBACK.md`
- `docs/live-trading/LIVE_LAUNCH_ARCHITECTURE.md`(本次上线方案)
- `packages/live_trading/`(feature gates、risk engine、control plane、
  ledger、NAV、kill switches、reconciliation、gateway adapter)
- `packages/trading/`、`services/nautilus-runtime/`
- `.env.example`、`docker-compose.production.yml`、
  `docs/DEPLOYMENT_CHECKLIST.md`

## 工作项(按顺序)

### 1. 真实执行网关适配(消除 mock)

- 在 `packages/live_trading` 的 Execution Gateway 适配层实现真实交易所
  适配(现货,建议 Binance 现货先行,与 nautilus runtime 现有 adapter
  对齐):`submit_order / cancel_order / query_order / balances /
  positions / health`。
- 超时语义保持:`LIVE_TRADING_ORDER_TIMEOUT_SECONDS`(默认 8s)超时 →
  订单状态 `UNKNOWN`,**只查询、绝不盲目重试**。
- 凭据读取走现有 secret store(Fernet/KMS),plaintext 永不入库、
  永不进日志;连接权限硬校验:发现提现/转账/杠杆/合约/期权/做空
  权限 → 拒绝该连接并告警。
- 券商健康检查进入动态门:`status ∈ {CONNECTED, HEALTHY}` 才允许下单。
- 余额/持仓同步与每日对账闭环接真实数据源;对账差异 → 自动暂停
  该用户 Mandate + 告警(已有逻辑,接真实数据验证)。

### 2. 门控配置与上线顺序(严格按序,每步可回滚)

1. 测试网/小额联调,`LIVE_TRADING_GATEWAY` 指向真实适配但静态门
   仍全 OFF,用 admin 接口验证全链路诚实状态。
2. 配置 `.env`:`LIVE_TRADING_PROVIDER`、`LIVE_TRADING_VENUE`、
   `LIVE_TRADING_ALLOWED_SYMBOLS`(小白名单起步)、
   `LIVE_CREDENTIAL_ENCRYPTION_KEY`、`LIVE_TRADING_GATEWAY=nautilus`;
   确认 `NAUTILUS_ALLOW_WITHDRAWAL/TRANSFER/LIVE_TRADING_ENABLED/
   ALLOW_LIVE_ORDER` 全部保持 false。
3. 内部白名单:admin 通过 `live_user_approvals` 审批 1–2 个测试用户,
   Mandate 设极小 `max_notional`(≤ `LIVE_TRADING_DEFAULT_MAX_NOTIONAL`
   1000),走完 23 步管线首单,核对 Ledger/NAV/对账/trace_id。
4. 演练应急:全局 Kill Switch 开启/恢复、`LIVE_TRADING_ENABLED=false`
   重启回滚、数据库加密备份恢复(按 ROLLBACK.md)。
5. 全部通过后,最后置 `LIVE_TRADING_ENABLED=true` +
   `LIVE_TRADING_DEPLOYMENT_APPROVED=true`,灰度逐用户放量。

### 3. 部署

- 走 `docker-compose.production.yml`;确认 api/worker/scheduler 内存
  上限、日志滚动、加密异地备份、资源告警脚本仍然生效。
- Alembic 迁移链单 head,部署前 `alembic upgrade head` 干跑验证。
- 更新 `.env.example` 与 `docs/DEPLOYMENT_CHECKLIST.md` 的实盘章节。
- 前端配套:服务端插件 manifest 增加 `puregamma.live-trading` 条目
  (默认 disabled,门控开启后放行),供前端 Cordis 插件读取。

### 4. 验证与交付

- `pytest` 全绿;为真实网关适配补单测(超时→UNKNOWN、权限硬拒绝、
  对账差异→暂停);补一条端到端集成测试(审批用户小额下单全链路,
  可用测试网)。
- 交付物:网关适配代码、`.env` 配置样例、更新的 STATUS.md(mock 项
  清零说明)、上线 runbook(含每步回滚命令)、首单验证报告。

## 硬约束

- 不修改 PAPER/SHADOW 既有语义;LIVE 只走控制平面,旧运行时 LIVE
  保持关闭。
- 所有金额 `Numeric(20,8)`/Decimal,禁用 float。
- Ledger 只 INSERT;对账差异只追加 `reconciliation_adjustment`,
  历史永不改写。
- 任何一步不满足门控 → 状态诚实返回 `LIVE_DISABLED` + 逐项 checks,
  不得伪造成功。
- 提现/转账/杠杆/合约永远硬拒绝,无配置项可打开。
