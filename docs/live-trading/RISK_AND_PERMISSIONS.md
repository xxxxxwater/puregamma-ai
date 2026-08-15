# LIVE Trading — 风险与权限说明

## 1. 权限矩阵

| 主体 | 可以 | 不可以 |
| --- | --- | --- |
| DeepSeek Harness | 读取授权研究数据、生成报告/策略候选/Strategy Spec、PAPER/SHADOW 建议 | 读交易 Secret、调交易所 API、创建 LIVE Mandate、改风控、绕过用户确认/风险引擎、提交订单 |
| Agent / Memory | 对话、记忆、研究 | 直接下单、改风控 |
| Android / iOS / Web | 查看 NAV/持仓/订单/安全状态、发起预览与确认(经服务端授权) | 直连交易所、提交订单、计算最终 NAV |
| 普通管理员接口 | 查看、审批、Kill Switch、创建连接 | 绕过 Control Plane 直接下单 |
| Trading Control Plane | 全链路:审批→风控→幂等→网关→成交→Ledger→NAV | — |

`live_order` 作为 OrderIntent source 被**保留并硬拒绝**;`strategy` 来源的意图
不可直接确认,必须经用户重新确认(user_confirmed)。

## 2. 硬边界(第一版 LIVE)

- 一个交易所/券商;现货;白名单资产;小额资金;
- 提现/转账/杠杆/期货/期权/做空/跨账户全部禁用
  (`NAUTILUS_ALLOW_WITHDRAWAL/TRANSFER` 必须为 false,网关权限 JSON 亦禁止);
- Risk Engine 对 `max_leverage > 1` 直接拒绝。

## 3. 密钥与机密

- 数据库只存 Fernet 密文或 KMS 引用(`broker_connections.encrypted_credentials_ref`);
- `LIVE_CREDENTIAL_ENCRYPTION_KEY` 优先,缺省从 `ENCRYPTION_MASTER_KEY` 派生;
- API 任何端点不返回凭据;Harness 无任何密钥读取路径。

## 4. 不可篡改性

- `ledger_entries` / `risk_checks` / `fills` / `trading_reconciliations`
  由 ORM 事件拒绝 UPDATE/DELETE(与现有 CreditLedger/EvidenceSnapshot 同模式);
- 对账差异只新增 `reconciliation_adjustment`,绝不改历史。

## 5. 已知风险与缓解

| 风险 | 缓解 |
| --- | --- |
| 提交超时重复下单 | UNKNOWN 状态只查询、不重试;idempotency_key 唯一约束 |
| 行情缺失/异常 | 60s stale 窗口;NAV=NULL 不伪造;服务器时间戳 |
| 交易所断连 | 连接健康检查入账;对账失败自动暂停 Mandate |
| 服务器重启误恢复 | LIVE Mandate 默认不自动恢复(人工检查后恢复) |
| 单机过载 | 容器内存上限、worker ≤2、同步间隔上限、资源告警脚本 |

## 6. 未开放条件(LIVE 保持 DISABLED,详见 STATUS.md)

默认 `LIVE_TRADING_ENABLED=false` + `LIVE_TRADING_GATEWAY=mock` +
无用户审批 + 无 LIVE Mandate ⇒ 所有 LIVE 路径返回 LIVE_DISABLED。
