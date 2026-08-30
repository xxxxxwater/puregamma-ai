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

## 已完成(实盘开启批次,见 LIVE_LAUNCH_ARCHITECTURE.md)

- [x] **真实执行网关**:`packages/live_trading/binance_spot_gateway.py`
      (Binance 现货 REST,与 runtime `BinanceSpotTestnetAdapter` 同语义)
      — `submit_order / cancel_order / query_order / account_balances /
      positions / fetch_prices / health`,全协议覆盖;
- [x] **超时语义**:提交超时/传输失败/5xx → `GatewayOrderUnknown` → 订单
      `UNKNOWN`,只查询、绝不盲目重试;Binance 业务拒单(4xx)→ REJECTED
      ack(无重试歧义);时钟偏差 -1021 同步后重试一次;
- [x] **API Key 权限硬校验**:`/sapi/v1/account/apiRestrictions`
      发现提现/内部转账/万能转账/期权/合约/杠杆任一开启 → 连接
      `ERROR` + `UNSAFE_API_PERMISSIONS` + ops 告警,禁止下单(60s 缓存);
- [x] **凭据流**:凭据经 `secret_store`(Fernet/KMS)加密入库,网关按
      connection 解密,明文永不入库/入日志/入订单 ack;
- [x] **用户自助绑定**:`POST /api/trading/connections`(加密存储 + 立即
      健康/权限验证,不安全密钥被拒)、`POST /api/trading/connections/
      {id}/revoke`(撤销即暂停绑定 Mandate);
- [x] **余额/持仓/行情接真实数据**:`sync_live_balances_and_positions`
      经真实网关同步并写服务器行情;`refresh_live_market_prices` 优先
      用网关 ticker,失败回退 runtime 公共行情;每日对账走真实余额;
- [x] 网关选择:`LIVE_TRADING_GATEWAY=mock | nautilus | binance`,默认
      仍是 mock(诚实拒绝);
- [x] 前端配套:服务端插件 manifest 新增 `puregamma.live-trading`
      (默认 disabled,`LIVE_TRADING_ENABLED=true` 后放行);
- [x] 测试:新增 `tests/security/test_live_trading_gateway.py`
      (13 用例:超时→UNKNOWN 不重试、业务拒单、权限硬拒绝、签名与映射、
      端到端小额下单全链路、对账 ok/error、诚实 mock、绑定/撤销);
- [x] 上线 runbook:`LIVE_LAUNCH_RUNBOOK.md`;首单验证报告模板:
      `FIRST_ORDER_VERIFICATION.md`。

## 仍是 mock 的接口/能力

| 项 | 说明 |
| --- | --- |
| `LIVE_TRADING_GATEWAY=mock`(默认) | 默认网关:健康检查诚实返回 DISABLED,提交**不会**触碰任何券商;接真实券商前保持 mock |
| `NautilusExecutionGateway` | 适配层已实现;runtime 侧 LIVE 模式仍硬禁用(旧运行时 LIVE 保持关闭),此路径留给未来 runtime 化执行 |
| 真实券商凭证 | 代码链全通,生产凭证须按 runbook 由客户绑定并经审批后方可使用 |

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
6. `LIVE_TRADING_GATEWAY=mock`(默认);
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
