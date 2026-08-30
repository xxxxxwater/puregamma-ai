# PureGamma 实盘 LIVE — 首单验证报告(模板与证据清单)

> 在测试网演练与生产灰度中各执行一次。**只有本报告全部打勾,才允许
> 给下一批用户放量。** 所有时间戳用服务器时间,所有核对引用
> `trace_id`。

## 1. 基本信息

| 项 | 值 |
| --- | --- |
| 执行日期 / 操作人 | |
| 环境 | testnet 演练 / production 灰度(二选一) |
| 用户 / Mandate / 连接 | user=`…` mandate=`…` connection=`…` |
| 首单额度 | ≤ `LIVE_TRADING_DEFAULT_MAX_NOTIONAL`(1000) |
| 基础 URL(演练) | `LIVE_TRADING_BINANCE_BASE_URL=https://testnet.binance.vision` |
| 基础 URL(生产) | `LIVE_TRADING_BINANCE_BASE_URL=https://api.binance.com` |

## 2. 前置检查

- [ ] `GET /api/trading/safety-status`:静态门全绿、用户审批 approved、
      Mandate 审批 approved、连接 `CONNECTED/HEALTHY`、最新对账 `ok`、
      Kill Switch 全关;
- [ ] `POST /api/trading/connections/test`:health `HEALTHY` 且
      `permissions.safe=true`(提现/转账/合约/期权/杠杆全 false);
- [ ] `GET /api/frontend/plugins`:`puregamma.live-trading.enabled=true`。

## 3. 下单链路(逐项核对)

1. 预览:
   - [ ] `POST /api/trading/orders/preview` 返回 `intent` + `confirmation`
         + `trace_id`,risk checks 全 PASS;
   - [ ] 记录 `trace_id = ________`;
2. 确认:
   - [ ] `POST /api/trading/orders/confirm` 返回订单
         `status ∈ {accepted, filled}`、`broker_order_id` 非空;
   - [ ] 交易所侧(API 控制台)能看到同一 `client_order_id`;
3. 成交:
   - [ ] `puregamma.sync_live_order_statuses` 将订单推到
         `partially_filled/filled`;
   - [ ] `GET /api/trading/fills?order_id=` 有 Fill 记录
         (`broker_fill_id` 与交易所 trade id 一致);
4. 账本:
   - [ ] `GET /admin/trading/ledger`(或 DB)出现 `trade_buy/trade_sell` 与
         `fee` 条目,金额 Decimal 精确,`trace_id` 与第 3 步一致;
   - [ ] Ledger 无 UPDATE/DELETE(只追加);
5. NAV:
   - [ ] `GET /api/portfolio/nav`:`nav` 非空且 = 现金 + Σ(数量×最新价),
         `is_stale=false`;无价格时不伪造(=`null`);
6. 对账:
   - [ ] 手动跑 `puregamma.daily_live_reconciliation` → 最新
         `trading_reconciliations.status == ok`(交易所余额 vs Ledger vs
         NAV 在容差内);
   - [ ] 故意制造差异(如手动改一笔)→ 自动暂停 Mandate + ops 告警 →
         管理员恢复(演练项目);
7. 订单不重试:
   - [ ] 演练:提交超时订单为 `unknown`,`sync_live_order_statuses` 只
         查询不重发(交易所无第二笔)。

## 4. 应急演练(必须逐项通过)

- [ ] 全局 Kill Switch 开启 → 新单被拒,查询/撤单/记成交/对账仍可用;
- [ ] Kill Switch 管理员 release 后恢复;
- [ ] `LIVE_TRADING_ENABLED=false` 重启 → `LIVE_DISABLED`;
- [ ] 加密备份恢复演练成功(见 `ROLLBACK.md`)。

## 5. 结论

- [ ] 全部通过 → 允许按 runbook §4 灰度放量;
- [ ] 任一失败 → 保持 `LIVE_DISABLED`,按 `ROLLBACK.md` 回滚并复盘。

签名:__________ 日期:__________
