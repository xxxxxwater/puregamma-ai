# PureGamma.ai Product Requirements Document (PRD)

> **Version**: 1.0 — MVP Convergence  
> **Author**: PureGamma.ai Product Team  
> **Date**: 2026-07-06  
> **Status**: Draft for Review

---

## 1. One-Line Positioning

**PureGamma.ai 是唯一一个每天早上通过 iMessage 把"你的持仓 + 市场结构 + 风险"三合一推到你面前的 AI-native 加密投研 SaaS。**

> PureGamma.ai is the only AI-native crypto investment research SaaS that pushes a fused brief of your portfolio, market structure, and risk directly to your iMessage every morning.

---

## 2. Target ICP (Ideal Customer Profile)

### Primary ICP

| 维度 | 定义 |
|------|------|
| **身份** | Crypto active investor / small fund PM / family office CIO |
| **AUM** | $100K – $50M |
| **持仓类型** | BTC / ETH / SOL + 高 Beta + MSTR/STRC |
| **关键行为** | 每天早上需要了解市场状态、自己的 NAV、是否有风险事件 |
| **痛点** | 每天早上打开 5 个 Tab（TradingView / CoinGecko / Twitter / Glassnode / Excel）才能拼出全貌 |
| **核心需求** | "我不需要更多数据，我需要每天早上 3 分钟能看完的结论" |
| **付费意愿** | $29–$199/月 |
| **获客渠道** | Twitter/X crypto CT、crypto newsletters、referral |

### Secondary ICP

| 维度 | 定义 |
|------|------|
| **身份** | Quant / systematic trader exploring crypto |
| **AUM** | $500K – $20M |
| **关键行为** | 需要 backtest 基础设施但不想要 Bloomberg 的价格 |
| **付费意愿** | $199–$999/月（Enterprise） |

### 非目标用户 (Anti-ICP)

- 纯 TradFi 不碰 crypto 的投资者
- 只买 BTC ETF 不关心任何 research 的 passive holder
- 找交易信号/algo 自动跟单的人（PureGamma 不做执行）
- 期望"保证收益"的人（合规红线）

---

## 3. Product Core Value

### 3.1 核心价值主张

PureGamma 的价值不是"更多数据"，而是**每天早上 3 分钟的 fused conclusion**：

```
你的持仓 + 市场发生了什么 + 今天需要注意什么 = 一条 iMessage
```

### 3.2 三层价值

| 层级 | 功能 | 用户感知价值 |
|------|------|------------|
| **L1 — Daily Brief** | 每天早上 iMessage 推送 fused 结论 | "省了我 30 分钟早上拼信息的痛苦" |
| **L2 — Dashboard** | 深入研究、信号、playbook、回测 | "当我想深挖时有专业的工具" |
| **L3 — Portfolio NAV** | Plaid + CEX + Wallet 聚合 | "我看到的是我自己的钱，不是别人的" |

### 3.3 产品差异化

| 维度 | PureGamma | ChatGPT | TradingView | Bloomberg | Messari |
|------|-----------|---------|-------------|-----------|---------|
| **Push to iMessage** | ✅ 核心功能 | ❌ | ❌ | ❌ | ❌ |
| **Portfolio-aware** | ✅ NAV 融合 | ❌ | ❌ | ✅ (PORT) | ❌ |
| **Multi-source fusion** | ✅ KOL+链上+市场+宏观 | ❌ | ❌ | ✅ | ✅ |
| **Credit-controlled AI** | ✅ 每次消费可控 | ❌ | N/A | N/A | N/A |
| **价格** | $29–$199/mo | $20/mo | $15–$60/mo | $2,500/mo | $50–$500/mo |
| **Crypto-native** | ✅ 深度 | 通用 | 🟡 | ❌ | ✅ |
| **Nautilus backtest** | ✅ Max 以上 | ❌ | 🟡 Pine Script | ❌ | ❌ |

---

## 4. Product Differentiators (护城河)

### 4.1 每日 iMessage 触达（最强护城河）

- **用户不需要打开 App**，每天早上自动收到
- **换产品 = 失去早上的自动推送**，切换成本极高
- **iMessage 是个人空间**，不是邮件收件箱的垃圾堆
- **蓝 bubble** 在 iOS 生态中天然高信任

### 4.2 Portfolio-Aware Research

- ChatGPT 不知道你持有什么
- PureGamma 的报告是"你的 BTC 持仓 + 当前 funding rate + 你的风险暴露"的融合
- 这不是 generic market commentary，这是 personalized risk brief

### 4.3 Multi-Source Data Fusion

- 单一数据源（如只看 CoinGecko）价值有限
- 融合 KOL 情绪 + 链上 + funding + OI + 宏观 = 真实 alpha 信号
- 每个数据源的权重和可靠性都是透明的

### 4.4 Credit-Controlled AI Workflows

- 每次 LLM 调用消费 credit，用户看到成本
- 防止滥用，保证 unit economics
- 高端功能（X KOL 扫描 20 credits、backtest 25 credits）自然引导升级

### 4.5 NautilusTrader Research Layer

- 不是 Pine Script 的玩具回测
- 是专业级 Python 策略框架
- Max 以上可用，直接对标 quant 用户

---

## 5. MVP 范围总览

### Must-Have for MVP（第一版必须上线）

| 模块 | 范围 |
|------|------|
| **用户系统** | Email sign up + mock onboarding |
| **Daily Market Brief** | 基于 shared intelligence 的市场日报 |
| **iMessage Daily Push** | Max plan 用户每天一条 iMessage |
| **Dashboard** | 市场概览 + 最新信号 + 数据健康 |
| **Signal Engine** | 融合评分信号（market + sentiment + risk） |
| **Reports** | 日报 + 事件报告 |
| **Stripe Subscription** | Free / Pro / Max 三档，checkout + webhook + entitlement |
| **Credit System** | 消费扣减 + 月度重置 + 余额展示 |
| **Mock Data** | 所有数据源默认 mock，真实 API key 可替换 |
| **Disclaimer** | 所有页面和消息带 "This is not financial advice." |
| **iMessage Relay** | macOS self-host relay 或 mock provider |

### Should-Have for Beta

| 模块 | 范围 |
|------|------|
| **Portfolio NAV (基础版)** | Mock portfolio 展示，真实连接推迟 |
| **Telegram / Email 推送** | 非 iMessage 渠道 |
| **Playbook 生成** | 策略 playbook |
| **CoinGecko 真实数据** | 替换 mock market data |
| **User Preferences** | 关注资产 + 研究风格 + 推送时间设置 |
| **基础 admin 面板** | 用户管理 + subscription 状态查看 |

### Later (3-6 个月)

| 模块 | 范围 |
|------|------|
| **Plaid 真实连接** | 美股券商 holdings |
| **CEX Read-only 连接** | Binance / Coinbase read-only API |
| **On-chain Wallet** | ETH/SOL 钱包余额扫描 |
| **X KOL Sentiment** | X API 情绪数据 |
| **Nautilus Backtest (真实)** | 真实 backtest 引擎 |
| **Coinglass / Glassnode / DefiLlama** | 高级数据源 |
| **Bloomberg Import** | Enterprise 专属 |
| **Nautilus Paper Trading** | Max/Enterprise |
| **Team Workspace** | Enterprise |

### Explicitly NOT in MVP

| 模块 | 原因 |
|------|------|
| **Live Trading** | 合规风险，永远 disabled by default |
| **Nautilus Live Trading** | 同上 |
| **Bloomberg Terminal 集成** | 成本和复杂度，推迟到 Enterprise |
| **X KOL 实时扫描** | API 成本高，推迟到 Max |
| **Plaid 真实连接** | Plaid 审批时间长，MVP 用 mock |
| **自动交易 / 跟单** | Never. 产品底线 |
| **AI 投资建议** | 只做 research，不做 advice |
| **Custody / 资金托管** | Never |

---

## 6. SaaS Plan 最终设计

### Free Plan

| 维度 | 定义 |
|------|------|
| **目标** | 获客漏斗顶部，让用户体验产品价值 |
| **价格** | $0 |
| **月 credit** | 30 |
| **每日报告数** | 1 |
| **数据源** | Mock market data only |
| **通知渠道** | Email only |
| **iMessage** | ❌ |
| **X KOL / On-chain / 高级数据** | ❌ |
| **Backtest** | ❌ |
| **Portfolio NAV** | ❌ |
| **核心升级触发点** | "Unlock iMessage daily brief → Upgrade to Max" |

### Pro Plan

| 维度 | 定义 |
|------|------|
| **目标用户** | Individual active crypto investor |
| **价格** | $29.90/月 |
| **月 credit** | 1,000 |
| **每日报告数** | 1 |
| **数据源** | Market + RSS + basic |
| **通知渠道** | Telegram + Email |
| **iMessage** | ❌ (Max 专属) |
| **Backtest** | ❌ (Max 专属) |
| **Portfolio NAV** | ❌ (Max 专属) |
| **核心升级触发点** | "Get iMessage daily brief + Portfolio NAV → Upgrade to Max" |

### Max Plan

| 维度 | 定义 |
|------|------|
| **目标用户** | Serious crypto investor / small fund |
| **价格** | $199.00/月 |
| **月 credit** | 10,000 |
| **每日报告数** | 5 |
| **数据源** | Market + RSS + X KOL + On-chain + Coinglass + Glassnode |
| **通知渠道** | Telegram + Slack + Email + **iMessage** |
| **iMessage** | ✅ 核心功能 |
| **Backtest** | ✅ 高级回测 |
| **Portfolio NAV** | ✅ 完整 portfolio 聚合 |
| **Playbook** | ✅ 策略 playbook |
| **核心升级触发点** | "Add Bloomberg + Custom KOL + Team workspace → Enterprise" |

### Enterprise Plan

| 维度 | 定义 |
|------|------|
| **目标客户** | Crypto fund / family office / quant team |
| **定价方式** | Custom quote (annual contract) |
| **月 credit** | 50,000+ |
| **所有 Max 功能** | ✅ |
| **Bloomberg Import** | ✅ 授权适配器 |
| **Custom KOL List** | ✅ 自定义 KOL 列表 |
| **Custom Data Source** | ✅ API / private deployment |
| **Team Workspace** | ✅ 多人协作 |
| **SLA** | 99.5%+ uptime |
| **Security Review** | ✅ 第三方安全审计 |
| **Private Deployment** | ✅ 可选 |

---

## 7. Credit Cost Model (当前确认)

| Action | Credits | Plan Required |
|--------|---------|---------------|
| `daily_market_report` | 10 | Free+ |
| `event_report` | 5 | Free+ |
| `sentiment_scan` | 8 | Pro+ |
| `x_sentiment_scan` | 20 | Max+ |
| `onchain_scan` | 12 | Max+ |
| `backtest` | 25 | Max+ |
| `playbook_generation` | 30 | Max+ |
| `telegram_alert` | 1 | Pro+ |
| `slack_alert` | 1 | Max+ |
| `email_alert` | 1 | Free+ |
| `imessage_alert` | 3 | Max+ |

---

## 8. 关键产品决策

### 决策 1: iMessage 是 Max 专属功能

**理由**:
- iMessage 是 PureGamma 的最强护城河和留存引擎
- 需要 Mac relay 基础设施，成本较高
- 如果 Free/Pro 有 iMessage，Max 失去升级动力
- Free 用户通过 Email、Pro 用户通过 Telegram 体验推送，Max 解锁 iMessage

### 决策 2: Portfolio NAV 是 Max 功能，非 MVP 核心

**理由**:
- Plaid / CEX / Wallet 真实连接在 MVP 阶段不可控（Plaid 审批 4-8 周）
- Mock portfolio 可以在 dashboard 展示，但真实连接推迟
- Portfolio NAV 是 Max 的核心升级动力

### 决策 3: NautilusTrader 是 Max 功能

**理由**:
- Backtest 是 quant 用户的核心需求
- 每次 backtest 消耗 25 credits，Free/Pro 的 credit 不够
- 放在 Max 可以支撑 $199 价格点

### 决策 4: X KOL / Bloomberg 是高成本数据，放在 Max/Enterprise

**理由**:
- X API 费用高（$100–$5,000/月 depending on tier）
- Bloomberg 授权复杂，需要 Enterprise sales 流程
- 这是 Max $199 和 Enterprise custom 的核心价值支撑

### 决策 5: Live Trading 永远 disabled

**理由**:
- PureGamma 定位是 research，不是 execution
- 合规风险太高
- 明确区分于 trading bot / copy trading 产品

---

## 9. 产品风险 (Top 10)

| # | 风险 | 严重程度 | 缓解措施 |
|---|------|---------|---------|
| 1 | **iMessage relay 不稳定** — macOS relay 依赖用户自己的 Mac | 🔴 HIGH | Mock provider for demo; 文档清晰说明 relay 限制 |
| 2 | **Plaid 审批周期长** — 可能 4-8 周才能上线 | 🔴 HIGH | MVP 用 mock portfolio; 不依赖 Plaid 上线 |
| 3 | **X API 成本爆炸** — KOL 扫描消耗大量 API 调用 | 🟡 MEDIUM | Credit 控制 + 频率限制 + 结果缓存 |
| 4 | **LLM 幻觉** — 市场报告可能包含错误信息 | 🔴 HIGH | 所有报告带 disclaimer; 用户反馈机制; 数据源可追溯 |
| 5 | **用户期望自动交易** — 看到 backtest 就想 live trading | 🟡 MEDIUM | 明确产品定位; 永远 disabled; 文档和教育 |
| 6 | **竞品模仿 iMessage 推送** — 护城河不够深 | 🟡 MEDIUM | 先发优势 + portfolio-aware 融合难以复制 |
| 7 | **Credit 模型单位经济** — LLM 成本可能高于 credit 定价 | 🟡 MEDIUM | 持续监控 cost per action; 调整 credit cost 或 plan 价格 |
| 8 | **用户不知道产品能做什么** — onboarding 不清晰 | 🔴 HIGH | Mock onboarding flow; guided first report; 尽快让用户看到价值 |
| 9 | **Mock 模式和真实模式差距大** — 用户从 mock 切换到真实失望 | 🟡 MEDIUM | Mock 数据标注清晰; 渐进式真实数据接入 |
| 10 | **合规风险** — crypto + investment research 监管不确定 | 🔴 HIGH | "Not financial advice" 在所有输出中; 不托管资金; 不执行交易 |

---

## 10. 验收标准 (MVP Launch Criteria)

### 产品体验标准
- [ ] 新用户从 sign up 到看到第一份 daily brief < 3 分钟
- [ ] Dashboard 加载时间 < 2 秒
- [ ] 所有页面 mobile responsive
- [ ] Mock mode 下所有功能可演示

### 计费标准
- [ ] Stripe Checkout 创建 + webhook 处理完整闭环
- [ ] 订阅升级/降级/取消全部正常
- [ ] Credit 消费和余额实时准确
- [ ] `invoice.paid` 正确充值 monthly credits
- [ ] `invoice.payment_failed` 正确限制功能

### iMessage 标准
- [ ] macOS relay 可正常发送
- [ ] Idempotency 防止重复发送
- [ ] 消息长度限制生效
- [ ] 日发送限制生效
- [ ] 失败重试和退款机制正常

### 数据管道标准
- [ ] Mock data 覆盖全部 6 个资产
- [ ] Market snapshot 每 15 分钟刷新
- [ ] Shared intelligence 每天 00:00 UTC 生成
- [ ] 数据源状态正确展示

### 安全标准
- [ ] JWT auth 正常工作
- [ ] Stripe webhook signature 验证
- [ ] iMessage relay HMAC 签名验证
- [ ] 无明文 secret 在代码中

### 合规标准
- [ ] 所有 report 包含 "This is not financial advice."
- [ ] 所有 iMessage 包含 disclaimer
- [ ] 所有 signal 包含 invalidation condition
- [ ] KOL sentiment 标注 "an input, not a verified fact"

### 文档标准
- [ ] PRD 完成
- [ ] MVP Scope 文档完成
- [ ] User Personas 完成
- [ ] User Journey 完成
- [ ] SaaS Plans 完成
- [ ] iMessage Brief Spec 完成
- [ ] Launch Checklist 完成
- [ ] README 更新

---

## 11. 附录: 文件索引

| 文件 | 描述 |
|------|------|
| [PRD.md](PRD.md) | 本文档 — 产品总需求 |
| [MVP_SCOPE.md](MVP_SCOPE.md) | MVP 范围收敛详情 |
| [USER_PERSONAS.md](USER_PERSONAS.md) | 四类用户画像 |
| [USER_JOURNEY.md](USER_JOURNEY.md) | 完整用户旅程 |
| [SAAS_PLANS.md](SAAS_PLANS.md) | SaaS Plan 详细设计 |
| [DAILY_IMESSAGE_BRIEF_SPEC.md](DAILY_IMESSAGE_BRIEF_SPEC.md) | iMessage 产品规格 |
| [PRODUCT_ROADMAP.md](PRODUCT_ROADMAP.md) | 产品路线图 |
| [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) | 上线检查清单 |
| [METRICS.md](METRICS.md) | 产品指标体系 |
| [BACKLOG.md](BACKLOG.md) | Issue Backlog |

---

> **This document is a living artifact. Last updated 2026-07-06.**
