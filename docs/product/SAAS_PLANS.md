# PureGamma.ai — SaaS 套餐设计

**版本**: v1.0  
**日期**: 2026-07-06

---

## 定价哲学

PureGamma.ai 按**研究能力**分层定价，而非按功能数量。每一层解锁新的研究维度：

- **Free**: 体验 AI 研究能力
- **Pro**: 个性化研究（Portfolio-Aware）
- **Max**: 专业级研究（Multi-Source + iMessage）
- **Enterprise**: 机构级研究（Custom + Private）

---

## 套餐对比

| 维度 | Free | Pro | Max | Enterprise |
|------|------|-----|-----|------------|
| **月费** | $0 | $29.9 | $199 | Custom |
| **目标用户** | 体验者 | 活跃零售投资者 | 专业投资者 / 小型基金 | 机构 / 家族办公室 |
| **月度信用** | 30 | 1,000 | 10,000 | 50,000+ |
| **每日报告上限** | 1 | 1 | 5 | 100 |
| **告警上限/日** | 0 | 20 | 500 | 10,000 |

### 数据源权限

| 数据源 | Free | Pro | Max | Enterprise |
|--------|------|-----|-----|------------|
| Mock / Delayed Market | ✅ | ✅ | ✅ | ✅ |
| RSS News | ❌ | ✅ | ✅ | ✅ |
| CoinGecko Real-time | ❌ | ✅ | ✅ | ✅ |
| X KOL Sentiment | ❌ | ❌ | ✅ | ✅ |
| On-chain (Glassnode/Coinglass) | ❌ | ❌ | ✅ | ✅ |
| Bloomberg Adapter | ❌ | ❌ | ❌ | ✅ |
| Custom Data Source | ❌ | ❌ | ❌ | ✅ |
| API Access | ❌ | ❌ | ❌ | ✅ |

### 研究工具

| 工具 | Free | Pro | Max | Enterprise |
|------|------|-----|-----|------------|
| Daily Market Report | ✅ | ✅ | ✅ | ✅ |
| Event Report | ✅ | ✅ | ✅ | ✅ |
| Sentiment Scan | ❌ | ✅ | ✅ | ✅ |
| Signal Generation | ❌ | ✅ | ✅ | ✅ |
| Playbook Generation | ❌ | ❌ | ✅ | ✅ |
| Basic Backtest | ❌ | ✅ | ✅ | ✅ |
| Advanced Backtest | ❌ | ❌ | ✅ | ✅ |
| Portfolio NAV (手动) | ❌ | ✅ | ✅ | ✅ |
| Portfolio NAV (自动) | ❌ | ❌ | ✅ | ✅ |
| Nautilus Paper Trading | ❌ | ❌ | ✅ | ✅ |

### 推送渠道

| 渠道 | Free | Pro | Max | Enterprise |
|------|------|-----|-----|------------|
| Email | ✅ | ✅ | ✅ | ✅ |
| Telegram | ❌ | ✅ | ✅ | ✅ |
| Slack | ❌ | ❌ | ✅ | ✅ |
| iMessage | ❌ | ❌ | ✅ | ✅ |

### 企业功能

| 功能 | Free | Pro | Max | Enterprise |
|------|------|-----|-----|------------|
| Team Workspace | ❌ | ❌ | ❌ | ✅ |
| Custom KOL List | ❌ | ❌ | ❌ | ✅ |
| Private Deployment | ❌ | ❌ | ❌ | ✅ |
| SLA | ❌ | ❌ | ❌ | ✅ |
| Security Review | ❌ | ❌ | ❌ | ✅ |
| PDF Export | ❌ | ❌ | ✅ | ✅ |

---

## 各套餐价值表达（非功能列表）

### Free — "体验 AI 研究"
**一句话**: 用 PureGamma 看看 AI 怎么做 crypto 研究。
**核心体验**: 每天收到一份市场简报（web），了解 AI 研究的输出格式。
**升级触发**: 想看 Portfolio 分析 → 升级 Pro；想收到 iMessage → 升级 Max。

### Pro — "你的投资组合，AI 研究"
**一句话**: 把你的持仓变成 AI 研究的上下文。
**核心体验**: Portfolio-Aware Research — 研究不再是泛泛的，而是关于你的仓位。
**定价理由**: $29.9/mo = 1 次晚餐的价格，但每天节省 30 分钟研究时间。
**升级触发**: 想要 X KOL 情绪扫描、链上数据、iMessage 推送 → 升级 Max。

### Max — "专业研究，每日推送"
**一句话**: 机构级研究能力，每日 iMessage 触达。
**核心体验**: 多源数据融合 + 每日 iMessage Brief + 策略回测。
**定价理由**: $199/mo 对比 Bloomberg $2,500/mo/seat，提供 crypto-native 替代方案。
**升级触发**: 需要 Bloomberg 数据、定制 KOL、私有部署 → 联系 Enterprise。

### Enterprise — "你的研究基础设施"
**一句话**: 把 PureGamma 部署在你的基础设施上，用你的数据源。
**核心体验**: 定制化、私有化、可审计。
**定价方式**: 按年合同，基于用户数 + 数据源定制报价。$2,000 – $10,000 / mo。

---

## 信用额度经济学

### 为什么用信用额度而不是无限调用？
1. **成本控制**: 每次 LLM 调用 + 数据拉取有真实成本
2. **用户行为**: 让用户意识到"研究是有成本的"，避免滥用
3. **升级动机**: 用光信用额度 → 自然升级

### 月度信用够用吗？

| Plan | 月度信用 | 典型用户行为 | 可用次数 |
|------|---------|-------------|---------|
| Free | 30 | 3 份日报 | ~3 天 |
| Pro | 1,000 | 1 份日报/天 + 3 次 sentiment scan + 20 条 Telegram | ~30 天 |
| Max | 10,000 | 5 份日报/天 + 每日 iMessage + on-chain scan + backtest | ~30 天 |
| Enterprise | 50,000+ | 高频使用 + 团队共享 | 充足 |

### 信用超支处理
- 信用不足时：拒绝操作 + 提示升级
- 无自动购买信用包（MVP 不做）
- 无信用结转（每月重置）

---

## 升级路径设计

```
Free ──(看到 Portfolio 价值)──→ Pro ──(需要 iMessage / X KOL)──→ Max ──(需要 Bloomberg / Private)──→ Enterprise
  │                                │                                    │
  └──(信用不够用)──→ Pro           └──(信用不够用)──→ Max              └──(定制需求)──→ Sales
```

### 关键升级触发点

1. **Free → Pro**
   - 用户点击 Portfolio 页面 → 提示 "Connect your portfolio (Pro required)"
   - 信用额度用完 → 提示 "Upgrade to Pro for 1,000 credits/mo"
   - 用户想连接 Telegram → 提示 "Telegram alerts require Pro"

2. **Pro → Max**
   - 用户点击 iMessage 设置 → 提示 "iMessage Daily Brief requires Max"
   - 用户点击 X KOL 数据源 → 提示 "X KOL sentiment requires Max"
   - 用户想运行 on-chain scan → 提示 "On-chain scanning requires Max"

3. **Max → Enterprise**
   - 联系销售 → 定制报价
   - 试用期 14 天

---

## 与竞品价格对比

| 产品 | 月费 | 定位 |
|------|------|------|
| PureGamma Free | $0 | AI 研究体验 |
| PureGamma Pro | $29.9 | Portfolio-Aware Research |
| PureGamma Max | $199 | 专业级 crypto research |
| PureGamma Enterprise | Custom | 机构定制 |
| Bloomberg Terminal | $2,500 | 全市场终端 |
| Messari Pro | $75 | Crypto 研究 |
| Glassnode Advanced | $49 | On-chain 分析 |
| TradingView Premium | $59.95 | 图表 + 社区 |
| Koyfin Plus | $55 | 股票研究 |
| ChatGPT Plus | $20 | 通用 AI |

**PureGamma Max ($199) = Messari Pro ($75) + Glassnode ($49) + TradingView ($60) + AI 合成 + iMessage 推送**

---

## 套餐设计原则

1. **Free 不是无限试用，而是有限体验**
   - 30 credits 用完后无法生成新报告
   - 不给 iMessage（那是 Max 的核心价值）
   - 不给 Portfolio（那是 Pro 的核心价值）

2. **Pro 是最大用户群**
   - 定价 $29.9 是心理舒适区
   - Portfolio NAV 是 Pro 的核心差异化

3. **Max 是高价值功能集合**
   - iMessage + X KOL + On-chain 绑定
   - 这些功能有真实 API 成本，必须收费

4. **Enterprise 是定制化**
   - 不定价，按需报价
   - 收入主要来源但用户量少
