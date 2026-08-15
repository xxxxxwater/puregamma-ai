# LIVE Trading — 交付状态清单

## 已完成(本批次)

- [x] Alembic 迁移 0026(single head,round-trip 验证)
- [x] 数据模型:BrokerConnection / TradingMandate 扩展 / OrderIntent(LIVE)
      / RiskCheck / Order / Fill / Immutable Ledger / NAV Snapshot /
      Kill Switch / 用户审批 / 对账记录
- [x] Risk Engine(14 类检查,Decimal,版本化,不可篡改)
- [x] Trading Control Plane(23 步顺序、行锁、幂等、UNKNOWN 只查询不重试、
      trace_id)
- [x] Immutable Ledger(追加式,ORM 拒绝 UPDATE/DELETE,9 类 entry_type)
- [x] NAV Calculator(服务器计算、60s stale→NULL 不伪造、成交后触发、
      30–60s 定时、版本与价格时间记录)
- [x] Execution Gateway 适配层(Nautilus 适配 + 诚实 mock)
- [x] 每日对账(差异→暂停 Mandate、禁止新订单、保留同步、管理员告警、
      不改历史 Ledger)
- [x] Kill Switch(global/user/mandate/connection;触发后允许查询/撤单/
      记成交/对账;人工恢复)
- [x] 审计日志(trace_id、append-only)
- [x] Secret 管理(Fernet 密文/KMS 引用,无明文入库)
- [x] 接口:14 个要求端点全部实现
- [x] Celery 任务 + 调度(5 任务,预算内)
- [x] 部署:内存上限(已有)、日志限制、加密异地备份脚本、资源告警脚本
- [x] 文档 8 份;测试 16 个新用例 + 迁移链更新

## 仍是 mock 的接口/能力

| 项 | 说明 |
| --- | --- |
| `LIVE_TRADING_GATEWAY=mock` | 默认网关:健康检查诚实返回 DISABLED,提交**不会**触碰任何券商;接真实券商前保持 mock |
| `NautilusExecutionGateway` | 已实现适配(nautilus runtime `submit_order` 等),但真实交易所 API 凭据/授权尚未接入,`submit_order` 在 runtime 侧仍为 paper/mock |
| `POST /api/trading/connections/test` | 走 Gateway 健康检查;mock 网关下返回 DISABLED(诚实) |
| 余额/持仓同步 | 经 Gateway 适配;mock 网关返回不可用,Ledger 派生数据不受影响 |

## 仅支持 PAPER 的能力

- 既有 `/trading/*`(orders preview/confirm、runtime sync、performance 等)全部
  保持 PAPER/SHADOW 语义,未做任何改动。

## 仅支持 SHADOW 的能力

- 既有 Shadow 策略运行与 `execution_mode=shadow` 的 Mandate,未改动。

## 仍不满足 LIVE 的条件(默认)

1. `LIVE_TRADING_ENABLED=false`(默认);
2. `LIVE_TRADING_DEPLOYMENT_APPROVED=false`(默认);
3. `LIVE_TRADING_PROVIDER` 未配置;
4. 无任何用户通过 `live_user_approvals` 审批;
5. 无 `execution_mode=live` 且已批准的 Mandate;
6. `LIVE_TRADING_GATEWAY=mock`(真实券商适配与凭据未接入);
7. 未完成真实交易所连接健康检查与对账。

⇒ 当前系统状态恒为 **LIVE_DISABLED**,所有 LIVE 接口诚实返回状态而非假数据。

## 如何一键关闭交易

1. 应用层(最快):
   `POST /admin/trading/kill-switch {"scope":"global","active":true,"reason":"..."}`
   — 禁止新订单,允许查询/撤单/记成交/对账。
2. 环境层(彻底):
   `LIVE_TRADING_ENABLED=false`(或 `LIVE_TRADING_DEPLOYMENT_APPROVED=false`)
   → 重启 api/worker/scheduler;`safety-status` 立即回到 LIVE_DISABLED。
3. 运行时既有接口仍可用:`POST /trading/runtime/kill-switch`(PAPER 运行时)。

## 如何恢复数据库和订单状态

见 `ROLLBACK.md`:加密备份恢复、`alembic downgrade 0025_harness_research`、
unknown 订单只查询不重发、Ledger 永不改写、重启后 LIVE Mandate 不自动恢复。
