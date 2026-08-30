# 提示词(前端工程师)— PureGamma 实盘 LIVE 控制台 UI

把下面整段作为任务提示词发给前端工程师:

---

你是 PureGamma AI 的前端工程师。仓库是 Next.js(en/zh 双语),前端扩展
运行时是 **Cordis**(`apps/web/plugins/`,cordis 3.18.1)。后端已完成
LIVE Trading Control Plane(23 步管线、风控、Kill Switch、不可篡改
Ledger、服务端 NAV),你的任务是:**为实盘 LIVE 交易构建一套简洁大气、
可组合的插件化前端控制台**。只做前端,不改 API 语义。

## 必读(动手前全部读完)

- `docs/live-trading/LIVE_LAUNCH_ARCHITECTURE.md`(本次架构方案)
- `docs/live-trading/FEATURE_FLAGS.md`、`docs/live-trading/STATUS.md`
- `apps/web/plugins/core/contracts.ts`(Cordis 契约与服务)
- `apps/web/plugins/core/runtime.tsx`
- `apps/web/plugins/builtin/trading/index.tsx`(现有 PAPER 插件,照此风格)
- `apps/web/plugins/builtin/{research,portfolio,options,secretary}/index.tsx`
- Glass 视觉系统相关组件(全局搜 `glass`,沿用其设计令牌)

## 交付物

### 1. 新内置插件 `apps/web/plugins/builtin/live-trading/`

`index.tsx` 满足 `FrontendPlugin` 契约:`id = "puregamma.live-trading"`,
`version = "1.0.0"`。在 `contracts.ts` 的 `FrontendPermission` 中新增
`"trade:live"`,插件声明 `permissions = ["read:portfolio", "trade:live"]`。
权限只是 UX 声明——所有真实权限由 FastAPI 强制。

### 2. 四个面板(通过 `ctx.panels.register` 注册,懒加载)

1. **`live.overview`(路由 `/trading/live`)** — 实盘总览:
   - 顶部安全状态条:调 `GET /api/trading/safety-status`,逐项渲染
     `checks`(静态门/审批/Kill Switch/连接健康/对账),状态为
     `LIVE_DISABLED` 时整页只显示诚实说明 + 申请入口,不渲染任何交易 UI。
   - NAV 卡片:`GET /api/portfolio/nav`;快照超过 60s(stale)必须显示
     `—`(NULL 语义),绝不显示旧数字当现值。
   - 连接健康、Mandate 审批状态、四级 Kill Switch 当前状态徽标。
2. **`live.connect`(路由 `/trading/live/connect`)** — 绑定交易所
   API Key:表单(api_key / api_secret / passphrase),显著提示用户创建
   「仅现货交易 + 读取,关闭提现/转账」的 key;提交到
   `POST /api/trading/connections`;前端绝不把明文写入
   localStorage/cookie/日志;绑定后调 `POST /api/trading/connections/test`
   展示健康结果(mock 网关返回 DISABLED 时如实展示)。
3. **`live.orders`(路由 `/trading/live/orders`)** — 下单与订单:
   - preview → confirm 两步:preview 响应里逐项展示 RiskCheck 结果
     (14 类检查,通过/拒绝及原因),被拒绝时 confirm 按钮禁用。
   - 未成交订单撤单;orders / fills 列表,每条显示 `trace_id`。
   - 所有 confirm 类操作必须二次确认对话框(展示数量、名义金额、
     标的、场所)。
4. **`live.account`(路由 `/trading/live/account`)** — 账户:
   余额、持仓、append-only Ledger 流水(9 类 entry_type 徽标)、
   最新对账状态、Mandate 限额(最大名义/日亏/白名单)与冷却/到期。

### 3. 一个全局命令

`ctx.commands.register`:`live.emergency-pause` —「暂停实盘新建仓」,
调用户级暂停接口(暂停自有 Mandate),出现在命令面板,二次确认。

### 4. Manifest 门控

插件注册前读取服务端插件 manifest 与 `safety-status`:manifest 不含
`puregamma.live-trading` 或端点 404/501 时,不注册面板,只在导航显示
「实盘(未开启)」禁用项。**能力缺失永远诚实显示,绝不伪造数据。**

## 设计与质量要求

- **简洁大气**:Glass 视觉系统;单列卡片、大留白;中性色 + 一个强调色;
  金额/数量用等宽数字(tabular-nums);LIVE 相关金额用 Decimal 字符串
  原样渲染,不做 float 运算。
- i18n:en/zh 全文案走 `messages/`,key 前缀 `liveTrading.*`。
- 可访问性:`prefers-reduced-motion`、语义化按钮、键盘可达。
- 状态机驱动:UI 只有 `LIVE_DISABLED / PENDING_APPROVAL / READY /
  PAUSED / KILLED` 几种由 `safety-status` 派生的状态,拒绝用零散布尔
  拼装。
- 测试:为门控逻辑与 NAV stale 显示补组件测试;Playwright 冒烟:
  mock `safety-status` 两种状态各截一张图。
- 构建通过 `pnpm --filter web build`,无新 lint 错误。

## 硬约束

- 不新增绕过 Cordis 契约的全局状态;数据流走 `ctx.api`。
- 不在前端实现任何风控计算——只做展示与意图提交。
- 不把任何凭据明文持久化;不向第三方域名发请求。
- 端点不存在/501 → 「功能不可用」;网关 mock → 显示 DISABLED;
  NAV stale → NULL。诚实优先于好看。
