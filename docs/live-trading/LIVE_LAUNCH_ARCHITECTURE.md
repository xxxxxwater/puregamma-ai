# PureGamma 实盘 LIVE 开启 — 上线架构方案

> 目标:在现有「LIVE Trading Control Plane」之上,把实盘从 `LIVE_DISABLED`
> 推进到「对通过审批的用户可用」的受控上线状态,并配套一套简洁大气、
> 基于 Cordis 插件化可组合界面的前端实盘控制台。

## 1. 现状盘点(代码已完成的部分)

后端控制面 **已交付且全部默认关闭**(见 `docs/live-trading/STATUS.md`):

- 23 步下单管线:ownership → mandate → 静态门 → 用户审批 → 券商健康 →
  白名单 → 名义/余额/持仓/日亏/杠杆/频率 → Kill Switch → 幂等 →
  不可篡改 RiskCheck → OrderIntent → 行锁 → Execution Gateway →
  broker_order_id → 成交流水 → 不可篡改 Ledger → NAV。
- 14 个 API 端点已实现:`/api/trading/mandates*`、
  `/api/trading/connections*`、`/api/trading/orders/*`、
  `/api/trading/safety-status`。
- Risk Engine(Decimal、版本化、14 类检查)、Immutable Ledger
  (INSERT-only)、每日对账(差异→暂停 Mandate)、4 级 Kill Switch、
  Fernet/KMS 凭据加密、服务端 NAV(60s stale → NULL 不伪造)。
- Admin 实盘面:`/admin/trading/*`(用户审批、Kill Switch、连接、
  Ledger、对账)。

**仍是 mock / 未接实盘的部分**(本次升级的核心工作):

| 缺口 | 位置 | 说明 |
| --- | --- | --- |
| 执行网关 | `LIVE_TRADING_GATEWAY=mock` | mock 网关诚实返回 DISABLED;需接入真实券商/交易所适配(现货) |
| 凭据写入 | `broker_connections` | 需要用户自助绑定交易所 API Key(Fernet 加密,只读+现货交易权限,提现/转账/杠杆硬拒绝) |
| 余额/持仓同步 | Gateway 适配层 | 真实连接下的同步与对账闭环 |
| 前端实盘 UI | `apps/web` | Trading 插件目前只注册 PAPER 面板,无实盘控制台 |

## 2. 开启实盘的门控模型(不可绕过)

两层评估,任一不满足 → 恒为 `LIVE_DISABLED`:

**静态门**(环境变量,全部满足):

```
LIVE_TRADING_ENABLED=true
LIVE_TRADING_DEPLOYMENT_APPROVED=true
LIVE_TRADING_PROVIDER=<binance|coinbase|...>   # 非空
LIVE_TRADING_GATEWAY=nautilus                  # 不再是 mock
NAUTILUS_ALLOW_WITHDRAWAL=false                # 提现硬禁
NAUTILUS_ALLOW_TRANSFER=false                  # 转账硬禁
NAUTILUS_LIVE_TRADING_ENABLED=false            # 旧运行时 LIVE 关
NAUTILUS_ALLOW_LIVE_ORDER=false                # 旧运行时下单关
LIVE_CREDENTIAL_ENCRYPTION_KEY=<Fernet key>
```

**动态门**(DB,按用户/Mandate):用户通过 `live_user_approvals` 审批 →
Mandate 已批准、`execution_mode=live`、`environment=production`、未暂停/
未撤销/未过期 → 四级 Kill Switch 全部关闭 → 券商连接
`status ∈ {CONNECTED, HEALTHY}` → 最新对账 `status == ok` → 风控限额/
白名单配置完整。

**上线顺序(建议):**

1. 完成真实执行网关适配 + 测试网/小额联调(STATUS.md 中 mock 项清零)。
2. 部署时保持静态门全 OFF,先上线前端与凭据绑定功能(只读验证)。
3. 内部白名单用户走完整审批链,`LIVE_TRADING_GATEWAY=nautilus`。
4. 逐用户开 `live_user_approvals`,设小额度 `max_notional`。
5. 最后才置 `LIVE_TRADING_ENABLED=true` +
   `LIVE_TRADING_DEPLOYMENT_APPROVED=true`,并演练全局 Kill Switch 与回滚
   (`docs/live-trading/ROLLBACK.md`)。

## 3. 前端架构:Cordis 可组合实盘控制台

参照 DSH Harness 的 profile/plugin 分层思想,前端沿用本仓库已有的
Cordis 运行时(`apps/web/plugins/`):

```
┌────────────────────────────────────────────────────┐
│ Next.js App Router(路由/渲染所有权不变)            │
│  ┌──────────────────────────────────────────────┐  │
│  │ Cordis Context(纯前端扩展运行时)              │  │
│  │  services: api / session / entitlements /     │  │
│  │  navigation / panels / commands / telemetry / │  │
│  │  realtime                                     │  │
│  │                                               │  │
│  │  ┌─────────────┐ ┌──────────────┐ ┌────────┐ │  │
│  │  │ trading     │ │ live.trading │ │ admin  │ │  │
│  │  │ (PAPER 已有)│ │ (新增插件)   │ │ (已有) │ │  │
│  │  └─────────────┘ └──────────────┘ └────────┘ │  │
│  └──────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────┘
        │  唯一可信边界:FastAPI(manifest 门控 + 全部风控)
        ▼
  /api/trading/safety-status → 驱动 UI 状态机
```

新增内置插件 `apps/web/plugins/builtin/live-trading/`:

- **server manifest 门控**:仅当 `/api/trading/safety-status` 返回非
  `LIVE_DISABLED` 且服务端 manifest 含 `puregamma.live-trading` 时注册;
  否则 UI 只显示诚实的「实盘未开启」面板(绝不渲染假数据)。
- **面板(panels)**:
  - `live.overview` — 安全状态条(门控逐项 checks)、NAV 卡片
    (stale 显示 NULL/灰态)、连接健康、Kill Switch 状态。
  - `live.connect` — 绑定交易所 API Key(引导用户开「只读+现货、
    禁提现」的 key;提交即加密,前端永不持久化明文)。
  - `live.orders` — preview → confirm 两步下单(展示 RiskCheck 结果)、
    未成交单撤单、orders/fills 列表(trace_id 可见)。
  - `live.account` — 余额/持仓/Ledger 流水(append-only 展示)、
    对账状态、Mandate 限额与审批状态。
- **命令(commands)**: emergency「停止新建仓」入口(调用户级
  kill switch / pause mandate),放在全局命令面板。
- **新增前端权限**:`"trade:live"` 加入 `FrontendPermission`,仅为 UX
  声明——真实权限永远在 API 侧。
- **设计语言**:沿用 Glass 视觉系统,简洁大气——大留白、单列卡片、
  单色 + 一个强调色;金额用等宽数字;所有 LIVE 操作二次确认;
  `prefers-reduced-motion` 可访问性;en/zh i18n。
- **诚实状态原则**(与后端一致):能力缺失/端点 404/501 → 显示
  「功能不可用」;NAV stale → 显示 NULL;网关 mock → 显示 DISABLED;
  永不伪造数据。

## 4. 分工

- **前端工程师** → `docs/live-trading/PROMPT_FRONTEND_LIVE_UI.md`
- **MVP/后端工程师** → `docs/live-trading/PROMPT_MVP_LIVE_BACKEND.md`
