# LIVE Trading — Feature Flag 文档

LIVE **不能只依赖一个环境变量**。系统在两层评估:

1. **静态门 `evaluate_static_gate()`** — 环境变量/部署标记,无 DB;
2. **全部门 `evaluate_full_gate(db, user_id, mandate, connection)`** —
   静态门 + 用户审批 + Mandate 审批 + Kill Switch + 连接健康 + 对账状态。

任一条件不满足 → 状态保持 **LIVE_DISABLED**,接口返回 `{state: "LIVE_DISABLED"}`
及逐项 `checks`。

## 静态门(必须全部满足)

| 条件 | 环境变量 | 默认 |
| --- | --- | --- |
| LIVE 总开关 | `LIVE_TRADING_ENABLED=true` | false |
| 部署标记 | `LIVE_TRADING_DEPLOYMENT_APPROVED=true` | false |
| 券商已配置 | `LIVE_TRADING_PROVIDER` 非空 | 空 |
| 提现必须禁用 | `NAUTILUS_ALLOW_WITHDRAWAL=false` | false |
| 转账必须禁用 | `NAUTILUS_ALLOW_TRANSFER=false` | false |
| 旧运行时 LIVE 必须关闭 | `NAUTILUS_LIVE_TRADING_ENABLED=false` | false |
| 旧运行时订单开关必须关闭 | `NAUTILUS_ALLOW_LIVE_ORDER=false` | false |

## 动态门(DB 条件,按用户/Mandate)

| 条件 | 来源 |
| --- | --- |
| 用户通过 LIVE 资格审批 | `live_user_approvals.status == approved` |
| Mandate 已批准且未暂停 | `trading_mandates.approval_status == approved && !paused` |
| Mandate 为 live/production | `execution_mode == live && environment == production` |
| Mandate 生命周期有效 | 未 revoked / 未 expired |
| 全局 Kill Switch 关闭 | `trading_kill_switches(scope=global)` |
| 用户级 Kill Switch 关闭 | `trading_kill_switches(scope=user)` |
| Mandate/连接级 Kill Switch 关闭 | `scope=mandate` / `scope=connection` |
| 券商连接健康且未撤销 | `broker_connections.status ∈ {CONNECTED, HEALTHY}` |
| 对账状态正常 | 最新 `trading_reconciliations.status == ok` |
| 风控配置完整 | mandate 各限额/白名单均已设置 |

## 其他相关开关

| 变量 | 含义 | 默认 |
| --- | --- | --- |
| `LIVE_TRADING_GATEWAY` | `mock`(默认,拒绝下单)/ `binance`(真实现货执行)/ `nautilus`(runtime 委托,预留) | mock |
| `LIVE_TRADING_VENUE` / `LIVE_TRADING_ALLOWED_SYMBOLS` | 场所 + 全局白名单 | MOCK / 空 |
| `LIVE_CREDENTIAL_ENCRYPTION_KEY` | 券商凭据 Fernet 密钥(不设则从 `ENCRYPTION_MASTER_KEY` 派生) | 空 |
| `LIVE_TRADING_ORDER_TIMEOUT_SECONDS` | 提交超时(超时→UNKNOWN,不重试) | 8 |
| `LIVE_TRADING_DEFAULT_MAX_NOTIONAL` | 审批默认最大名义金额 | 1000 |
| `LIVE_NAV_PRICE_STALE_SECONDS` | 价格 stale 窗口(超时 NAV=NULL) | 60 |
| `LIVE_TRADING_BINANCE_BASE_URL` | Binance 现货 REST 基址(演练可指向 `https://testnet.binance.vision`) | https://api.binance.com |
| `LIVE_TRADING_BINANCE_RECV_WINDOW_MS` | Binance 签名 recvWindow | 5000 |
| `LIVE_PRICE_REFRESH_INTERVAL_SECONDS` 等 | 同步预算 | 见 `.env.example` |

## 真实网关(Binance 现货)的附加行为

- **超时语义**:提交超时/传输失败/5xx → `UNKNOWN`,后续只查询
  (`/api/v3/order` + `/api/v3/myTrades`),绝不盲目重试;
- **权限硬校验**:API Key 在 `/sapi/v1/account/apiRestrictions` 上发现
  提现/内部转账/万能转账/期权/合约/杠杆任一开启 → 连接拒绝
  (`UNSAFE_API_PERMISSIONS`),与动态门「连接健康」叠加;
- **凭据**:每连接 Fernet 密文入库,网关按需解密,明文永不落库/日志/ack;
- 这些行为不改变门控模型:任一静态/动态门不满足,状态依然
  `LIVE_DISABLED`。

## 查看当前状态

- 用户: `GET /api/trading/safety-status`
- 运维: `GET /api/trading/safety-status` + admin 端点

## 如何一键关闭交易(详见 STATUS.md)

全局 Kill Switch:
`POST /admin/trading/kill-switch {"scope":"global","active":true,"reason":"..."}`
或环境层:`LIVE_TRADING_ENABLED=false` 后重启 API/worker。
