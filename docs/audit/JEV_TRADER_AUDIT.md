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

## 6. 许可证与署名

**MIT License**（`jarrodwatts/jev-trader`）。MIT 允许商用与再分发，要求保留版权声明与许可文本。
PureGamma 侧需：
1. 在展示页与 `THIRD_PARTY_NOTICES.md` 标注来源与 MIT；
2. 提供项目链接 https://github.com/jarrodwatts/jev-trader ；
3. 若复用其数据契约或代码片段，保留原版权头。

---

## 7. 未能确定 / 需注意

- 后端 `...railway.app` 为免费档，**无 SLA**。生产展示必须做断线降级与「数据已过期」标识，
  不能把上游可用性当作己方可用性。
- `quote.status` 在部分事件中缺失（样本最新块无 `quote`），展示层需容忍缺字段。
- 上游部署参数（`MODEL`、`DRY_RUN`）可被其所有者随时更改，
  **因此真实性标识必须每次由实时快照重算**。
