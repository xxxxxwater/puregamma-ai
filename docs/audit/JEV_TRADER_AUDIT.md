# Jev Trader 审计（P1）— 真实数据源与运行模式

审计时间：2026-09-18
方式：只读。未部署、未修改、未动用任何资金。

| 项目 | 值 |
|---|---|
| 演示站 | https://jev-trader.vercel.app/ （**纯静态前端**，`/history`、`/events` 均 404） |
| 实时后端 | `https://jev-trader-production.up.railway.app` |
| 开源仓库 | https://github.com/jarrodwatts/jev-trader |
| 许可证 | **MIT License** |
| 简介 | "One AI trade decision every Monad block. Jev on Kuru MON-USDC." |

---

## 1. 结论：三种状态中的哪一种

任务书要求区分三种状态。**实测结果是第 1 种**：

> ### 真实 Jev 推理 + 模拟成交（dry-run，无真实资金）

依据（全部来自实时后端 `GET /`，非 README、非页面文案）：

```json
{"model":"jev-latest", "wallet":null, "dryRun":true,
 "market":"0x065C9d28E428A0db40191a54d33d5b7c71a9C394"}
```

- `model = "jev-latest"` → **真实 Jev 模型**，不是 mock
- `dryRun = true` → 模拟成交
- `wallet = null` → **没有真实钱包，无真实资金**

### 独立证据（四条，互相独立，均可复现）

单看 `model` 字段不足以定论（字段是上游自己写的）。以下四条独立佐证：

**① 概率量化。** `/history` 中 **973 条非 late 决策，100%（973/973）** 的
`probabilities.buy` 都是 0.01 的整数倍（98 个不同取值）。
mock 走 `1/(1+exp(-signal))`，连续取值，**不可能**产生 100% 的两位小数。

**② 延迟下限。** 实测最小决策延迟 **65ms**；mock 无条件 `await Bun.sleep(80)`，
其 `latencyMs` 恒 ≥ 80ms。实测区间 65–340ms，均值 114.9ms。

**③ token 经济性（同时独立印证了我们的定价）。** 线上 `totals.jevUsd` = **$32.346402**，
对应 524,703 次决策 = **每次约 1,468 input tokens**。
按 TypeSafe 官方 $0.042/Mtok 计算完全吻合；而 mock 的
`inputTokens = JSON.stringify(state).length/4`（约 200–350）只能得到 $4.41–7.71，
**实测高出 4–7 倍**。

> 这条同时是我们**目录里 $0.042/Mtok 定价的独立交叉验证** —— 一个完全独立的第三方部署
> 在真实运行中产生的账单，反推出的单价与我们录入的价格一致。

**④ 成交侧反证。** 全部 1000 条历史事件中：`simulated` 恒为 `True`、
`txHash` 恒为 `None`、`gasMon` 与 `gasUsd` 恒为 **0**。
没有 wallet 对象就无法签名，因此**任何真实交易在结构上都不可能发生**。

### 价格数据是真实链上数据（已独立复核）

不是自述，而是自己直接读链：对 `https://rpc.monad.xyz` 直接调用 Kuru 市场的
`getL2Book()`（selector `0x46fdfbb1`）于区块 106058442 解出
`mid 0.024622 / spreadBps 6.09`；实时 feed 两个区块后（106058444）报
`mid 0.0246225 / spreadBps 6.09`。**价位与价差一致 → 行情确为真实链上数据。**

### ⚠️ README 已过期，不可采信

仓库 README 第 15 行仍写：

```
Deployed (dry run, mock model): https://jev-trader-production.up.railway.app
```

**这与实测不符。** 当前公开部署的 `model` 是 `jev-latest`（真实 Jev），不是 `mock`。
根因：`MODEL=mock|jev` 是部署侧环境变量（`.env.example` 中默认 `MODEL=mock`），
README 记录的是当时的部署参数，之后被改成 `jev` 而未更新文档。

> 这正好印证任务书的警告：**必须核实当前公开部署，而不是信任历史 README 或页面文案。**
> 展示页的真实性标识**必须以实时 `model` / `dryRun` 字段驱动**，不得硬编码，
> 否则上游一旦切回 mock，我们的页面就会说谎。

---

## 2. 真实数据来源（已核实到代码）

| 数据 | 来源 |
|---|---|
| 区块 / newHeads | `wss://rpc.monad.xyz`（WebSocket），另有轮询兜底 |
| 区块号 / Trade 日志 | `READ_RPC_URL=https://rpc.monad.xyz`，`eth_blockNumber` 轮询每 150ms + `eth_getLogs` |
| 订单簿 | Kuru DEX（Monad 上），经 `eth_call` 读取（公开 RPC 约 18ms/次，限 25 rps） |
| 发交易 | `RPC_URL=https://rpc.monad.xyz`，`eth_sendRawTransaction` |

链路：**Monad 区块链 → Kuru MON-USDC 订单簿 → Jev 模型 → 挂 post-only 限价单**。
每个 Monad 区块（约 300ms）产生一次决策，这是“实时高频”的来源。

---

## 3. 接口契约（实测 + 源码一致）

> ⚠️ **重要更正：线上部署的代码比仓库 HEAD 旧。**
>
> 本文档第 3 节的契约来自仓库 HEAD 的 `src/server.ts`，但**线上跑的不是 HEAD**。
> 实测线上事件字段为：
> `[bestAsk, bestBid, block, decision, fill, mid, position, spreadBps, totals, ts]`，
> 其中 `totals = [blocks, decisions, gasMon, gasUsd, jevUsd, lateBlocks, pnlMon, pnlPct, pnlUsd, realizedUsd, trades]`。
> 而 HEAD 的 `Totals` 用 `quotes/fills/reverted`，`BlockEvent` 有 `quote` 和 `resting`，`Fill` 有 `orderId`
> —— **这些在线上载荷里全都不存在**。形状与每块决策节奏对应 2026-09-16T22:16–22:32Z 的若干提交
> （`b79c8dc3a579`…`202bdcab2959`，或 `ca9fe4ad7515` 配 `DECIDE_EVERY_BLOCKS=1`）。
>
> **结论：不得把 README / SPEC.md / 仓库 HEAD 当作线上服务的描述。**
> P2 展示组件必须以**实测的线上字段**为准，并且对缺字段容错（例如部分事件没有 `quote`）。
> 另：线上未见 `ping` 事件（12s 窗口），HEAD 的 15s 心跳在旧构建中可能不存在 —— 因此
> **不能用 `ping` 作为存活判据**，应改用事件到达时间判断新鲜度。

后端 `src/server.ts`（Bun.serve），CORS 全开 `access-control-allow-origin: *`：

| 端点 | 说明 |
|---|---|
| `GET /` | 快照：`{model, wallet, dryRun, market, startedAt, latest}` |
| `GET /history` | 最近最多 1000 条 block 事件（实测返回 **1000** 条） |
| `GET /events` | **SSE 流**：连接即发 `snapshot`，随后每块一个 `block`，另有 `quote` / `fill` / `ping`（15s 心跳） |

事件类型：

```
event: snapshot   data: {...meta, history:[...]}
event: block      data: {block, ts, mid, bestBid, bestAsk, spreadBps, decision, fill, position, totals}
event: quote      data: {block, quote:{status: "sent"|"placed"|"reverted"|"lost"|"sim", orderId?, gasMon?}}
event: fill       data: {block, fill:{...}}          # taker 吃了我们的挂单
event: ping       data: <ms>
```

`decision` 字段（实测样本）：

```json
{"action":"sell", "probabilities":{"buy":0.03,"sell":0.97,"hold":0},
 "upIn10":0.03, "latencyMs":114, "late":false}
```

- `probabilities` 就是 **Jev 的原生概率分布**（buy/sell/hold），可直接展示
- `latencyMs` = 单次推理耗时（实测 ~114ms）
- `late: true` 且 `action: "hold"` 表示模型错过了该区块，未挂单

实测样本（`GET /history` 最新块 `106058421`）：`mid=0.024627`、
`bestBid=0.024623`、`bestAsk=0.024631`、`spreadBps=3.25`。

---

## 4. 可嵌入性

```
HTTP/2 200
access-control-allow-origin: *
server: Vercel
（无 X-Frame-Options，无 Content-Security-Policy）
```

- **iframe 未被禁止** → 技术上可嵌入
- **数据端点 CORS 全开** → 也可由 PureGamma 服务端或浏览器直接读取

**选型建议**：优先**原生 React 组件**读取后端只读接口，而非 iframe。理由：
1. 需要与 PureGamma 的浅色/深色主题、i18n、移动端一致，iframe 无法跟随主题；
2. 真实性标识必须由 `model`/`dryRun` 字段驱动，iframe 内无法读取；
3. 任务书要求「多用户同时访问时避免每个浏览器都向上游建立高成本重复连接」，
   需要服务端共享连接 —— iframe 做不到；
4. 原站是 Vercel 免费档，稳定性不由我们控制。

保留「访问原始演示站」外链作为补充。

---

## 5. 安全边界（本任务未越界）

- 全程**只读**：仅发 `GET /`、`GET /history`、`GET /events`
- **未配置任何交易私钥，未开启自动下单，未动用任何真实资金**
- 上游 `dryRun = true`、`wallet = null`，本身也不具备真实资金能力
- 展示层不代理任意 URL：只允许固定的上游主机

---

## 6. 许可证、署名与必须展示的声明

**MIT License**，需复现的版权行原文：

```
MIT License
Copyright (c) 2026 Jarrod Watts
```

义务边界：
- **仅 iframe 链接线上 URL** → 不构成再分发，**不触发**许可证义务；但仍应给出来源署名。
- **若 vendor / fork / 复用其代码或 `/events` 数据管线** → 构成再分发，
  **必须**随附完整 MIT 文本与上述版权行。

PureGamma 侧需：
1. 展示页与 `THIRD_PARTY_NOTICES.md` 标注来源与 MIT；
2. 提供项目链接 https://github.com/jarrodwatts/jev-trader ；
3. 若复用数据契约或代码片段，保留原版权头。

### 展示页必须显示的声明（建议文案）

任务书要求「有明确真实性标识」。由于线上是「真实模型 + 模拟成交」，
**既不能标成 mock（会低估披露），也不能标成真实交易（会误导）**：

> **Jev Trader — 第三方实时演示（dry-run）。**
> AI 决策与行情均为真实（Kuru/Monad 链上数据），但**订单与成交为模拟，无真实资金、无真实交易**。
> 不构成投资建议。来源：MIT © 2026 Jarrod Watts。

英文：

> **Jev Trader — third-party live demo (dry run).** AI decisions and prices are real
> (live Kuru/Monad on-chain data), but **orders and fills are simulated — no real funds,
> no real trades.** Not financial advice. Source: MIT © 2026 Jarrod Watts.

**该声明必须由实时 `model` / `dryRun` 字段驱动渲染，不得硬编码**——
上游一旦改回 `MODEL=mock`，硬编码的文案就会变成虚假陈述。

### iframe 的致命缺陷（决定 P2 选型）

iframe 技术上允许，但**被框住的整个页面无法从宿主注入任何内容** ——
**声明只能放在 frame 之外的宿主 DOM 里**。更关键的是，iframe 内部无法读取
`model`/`dryRun`，因此**无法做到「由真实状态驱动声明」**，只能写死。
这与任务书「不允许硬编码已上线」「真实性标识必须真实」的要求直接冲突。

**结论：P2 采用原生 React 组件**，不采用 iframe。

---

## 7. 未能确定 / 需注意

- 后端 `...railway.app` 为免费档，**无 SLA**。生产展示必须做断线降级与「数据已过期」标识，
  不能把上游可用性当作己方可用性。
- `quote.status` 在部分事件中缺失（样本最新块无 `quote`），展示层需容忍缺字段。
- 上游部署参数（`MODEL`、`DRY_RUN`）可被其所有者随时更改，
  **因此真实性标识必须每次由实时快照重算**。
