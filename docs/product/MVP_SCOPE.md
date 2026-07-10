# PureGamma.ai MVP Scope Convergence

> **Version**: 1.0  
> **Date**: 2026-07-06

---

## 1. MVP 收敛原则

### 核心问题

第一版到底卖什么？答案是：

> **每天早上一条 iMessage，把你的持仓和市场风险在一屏之内讲清楚。**

MVP 不做"功能最多的 crypto research 平台"。MVP 做"每天早上让你少打开 5 个 Tab 的产品"。

### 收敛三原则

1. **Push > Pull**: 用户不需要来 dashboard，我们来 push。iMessage 是核心交互。
2. **Fused > Raw**: 不提供原始数据表，提供融合后的结论。
3. **你的持仓 > 市场大盘**: 通用市场报告是 commodity。融合了你的持仓的报告是产品。

---

## 2. Must-Have (MVP Day 1)

### 2.1 用户系统

| 功能 | 范围 | 验收标准 |
|------|------|---------|
| Email + Password 注册 | ✅ | 注册 → verify → 登录完整闭环 |
| Mock Login (Demo) | ✅ | POST /auth/mock-login 可用 |
| JWT Auth | ✅ | Token 签发和验证 |
| User Profile | ✅ (最小) | Email, name, plan, credit_balance |
| User Preferences | ✅ (最小) | Preferred assets, risk level, notification channels |

**推迟**: OAuth (Google/Apple/Twitter)、2FA、team/workspace

### 2.2 Daily Market Intelligence

| 功能 | 范围 | 验收标准 |
|------|------|---------|
| Shared Market Intelligence | ✅ | 每天 00:00 UTC 生成一次 |
| Market Regime 判断 | ✅ | Risk-on / Risk-off / Neutral |
| Multi-asset coverage | ✅ | BTC, ETH, SOL, HYPE, MSTR, STRC |
| Signal Scanning | ✅ | Market structure + sentiment + risk scoring |
| Daily Report 生成 | ✅ | 每用户 personalised daily report |

### 2.3 iMessage Daily Push (核心功能)

| 功能 | 范围 | 验收标准 |
|------|------|---------|
| iMessage 发送 | ✅ | macOS relay 或 mock provider |
| Daily Brief 模板 | ✅ | Market-only / Combined |
| 消息长度限制 | ✅ | Max 3000 chars |
| 日发送限制 | ✅ | 20 per user per day |
| 发送时间设置 | ✅ | 用户可选时区和时间 |
| Idempotency | ✅ | 同一天同用户不重复 |
| Credit 消费 | ✅ | 3 credits per iMessage |
| Entitlement 控制 | ✅ | Max/Enterprise only |

### 2.4 Dashboard

| 功能 | 范围 |
|------|------|
| Market Regime Banner | ✅ |
| Asset Monitor Grid | ✅ |
| Top Signals Table | ✅ |
| Latest Report Preview | ✅ |
| Data Pipeline Health | ✅ |
| Credit Balance Display | ✅ |
| iMessage Status | ✅ |

### 2.5 Stripe Billing

| 功能 | 范围 |
|------|------|
| Checkout Session | ✅ |
| Customer Portal | ✅ |
| Webhook 处理 (7 events) | ✅ |
| Subscription 管理 | ✅ |
| Credit 月度充值 | ✅ |
| Payment Failed 处理 | ✅ |
| Mock Billing Mode | ✅ |

### 2.6 Credit System

| 功能 | 范围 |
|------|------|
| Credit 消费 | ✅ |
| Credit 余额查询 | ✅ |
| 月度重置 | ✅ |
| 余额不足处理 | ✅ |
| 退款机制 | ✅ |
| Credit Ledger 审计 | ✅ |

### 2.7 Disclaimer & 合规

| 要求 | 范围 |
|------|------|
| 全局 disclaimer | ✅ "This is not financial advice." |
| iMessage disclaimer | ✅ 每条消息 |
| KOL 标注 | ✅ "an input, not a verified fact" |
| Signal invalidation | ✅ 每个 signal |
| Live trading disabled | ✅ 永远 |

---

## 3. Should-Have (Beta)

| 模块 | 优先级 |
|------|--------|
| Telegram / Email 推送 | 🔴 HIGH |
| Portfolio NAV (Mock 版) | 🟡 MEDIUM |
| Playbook Generation | 🟡 MEDIUM |
| CoinGecko 真实数据 | 🔴 HIGH |
| Data Sources 页面 | 🟡 MEDIUM |
| 基础 Admin 面板 | 🟢 LOW |

---

## 4. Later (3-6 个月)

| 模块 | 优先级 |
|------|--------|
| Plaid 真实连接 | 🔴 HIGH |
| CEX Read-only | 🔴 HIGH |
| On-chain Wallet | 🟡 MEDIUM |
| X KOL Sentinel | 🔴 HIGH |
| Nautilus Backtest (真实) | 🟡 MEDIUM |
| Coinglass/Glassnode/DefiLlama | 🟡 MEDIUM |
| Nautilus Paper Trading | 🟢 LOW |
| Team Workspace | 🟢 LOW |
| Bloomberg Import | 🟢 LOW |

---

## 5. NOT in MVP (明确不做)

| 功能 | 原因 | 风险 |
|------|------|------|
| Live Trading | 产品定位 research, 非 execution | 🔴 合规 |
| Auto/Copy Trading | Never | 🔴 合规 |
| Custody/资金托管 | 需要牌照 | 🔴 合规/法律 |
| AI 投资建议 | 只做 research | 🔴 合规 |
| Bloomberg Terminal 实时集成 | $2,500/mo 成本 | 🟡 成本 |
| X KOL 实时监控 | API 费用高 | 🟡 成本 |
| Mobile App | Web 先验证 | 🟡 时间 |
| Multi-language | 英语先 | 🟡 时间 |
| Social Features | 非 MVP 价值 | 🟡 范围 |
| Custom Indicator Builder | 不需要 | 🟡 范围 |
| Real-time WebSocket | 不需要 | 🟡 范围 |

---

## 6. MVP 功能矩阵

| 模块 | MVP | Beta | Later | Never |
|------|:---:|:----:|:-----:|:-----:|
| User System (Email) | ✅ | — | — | — |
| User System (OAuth) | — | ✅ | — | — |
| Daily Market Intelligence | ✅ | — | — | — |
| Signal Engine | ✅ | — | — | — |
| Daily Report | ✅ | — | — | — |
| iMessage Daily Push | ✅ | — | — | — |
| Telegram Push | — | ✅ | — | — |
| Email Push | ✅ | — | — | — |
| Slack Push | — | — | ✅ | — |
| Dashboard | ✅ | — | — | — |
| Reports Page | ✅ | — | — | — |
| Signals Page | ✅ | — | — | — |
| Stripe Billing | ✅ | — | — | — |
| Credit System | ✅ | — | — | — |
| Portfolio NAV (Mock) | — | ✅ | — | — |
| Portfolio NAV (Real) | — | — | ✅ | — |
| Playbooks | — | ✅ | — | — |
| Data Sources Page | — | ✅ | — | — |
| Admin Panel | — | ✅ | — | — |
| Plaid | — | — | ✅ | — |
| CEX Read-only | — | — | ✅ | — |
| On-chain Wallet | — | — | ✅ | — |
| X KOL | — | — | ✅ | — |
| Nautilus Backtest | — | — | ✅ | — |
| Nautilus Paper Trading | — | — | ✅ | — |
| Coinglass/Glassnode | — | — | ✅ | — |
| Bloomberg | — | — | ✅ | — |
| Team Workspace | — | — | ✅ | — |
| Live Trading | — | — | — | ❌ |
| Auto/Copy Trading | — | — | — | ❌ |
| Custody | — | — | — | ❌ |

---

## 7. 当前项目 Gap 分析

| 差距 | 优先级 | 描述 |
|------|--------|------|
| Onboarding flow 缺失 | 🔴 BLOCKER | 没有引导用户从注册到第一个 daily brief 的 flow |
| iMessage 内容过于简单 | 🔴 BLOCKER | 当前只发 "report is ready"，不是真正的 fused brief |
| Portfolio-aware report 缺失 | 🔴 BLOCKER | 当前 report 是通用的，没有融合用户持仓 |
| 用户偏好设置不完整 | 🟡 HIGH | 缺少推送时间、研究风格选择 |
| 真实数据源替换 mock | 🟡 HIGH | CoinGecko 免费 API 应先接入 |
| Nautilus backtest mock | 🟡 MEDIUM | 前端完全 mock |
| Daily push 时间固定 | 🟡 MEDIUM | 当前固定 UTC 00:20 |

---

> **核心原则**: MVP 不是做最少的功能，而是做最少的、但能让用户付费的功能。
