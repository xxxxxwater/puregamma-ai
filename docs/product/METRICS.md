# PureGamma AI — 产品指标体系

**版本**: v1.0  
**日期**: 2026-07-06

---

## 一、核心指标框架

采用 **AARRR + Quality** 框架：

```
Acquisition → Activation → Retention → Revenue → Referral
                    ↓
               Quality Loop
```

---

## 二、Acquisition Metrics（获客）

| 指标 | 定义 | 目标 (Month 1) | 目标 (Month 3) |
|------|------|---------------|---------------|
| Landing Page Visits | 落地页 UV | 1,000 | 5,000 |
| Signup Rate | 注册数 / 落地页 UV | 5% | 8% |
| Signup Completion | 完成注册流程的用户数 | 50 | 400 |
| CAC (Customer Acquisition Cost) | 获客总成本 / 新付费用户 | <$50 | <$30 |
| Traffic Sources | 来源分布（organic/social/referral/paid） | Track | Optimize |

---

## 三、Activation Metrics（激活）

**Activation 定义**: 用户首次生成 Daily Report + 配置至少 1 个推送渠道。

| 指标 | 定义 | 目标 | 数据源 |
|------|------|------|--------|
| First Report Generated | 注册后 24h 内生成首份报告的用户% | >60% | Report.created_at |
| First Push Configured | 注册后 24h 内配置推送渠道的用户% | >40% | UserPreference |
| First iMessage Received | Max 用户首次收到 iMessage Brief | >80% (Max users) | NotificationDelivery |
| First Portfolio Sync | Pro 用户首次同步 portfolio | >30% (Pro users) | Integration events |
| Onboarding Completion Rate | 完成全部 3 步 onboarding 的用户% | >70% | Onboarding funnel |
| Time to Activation | 从注册到 Activation 的中位时间 | <1 day | Timestamp diff |

---

## 四、Retention Metrics（留存）

| 指标 | 定义 | 目标 | 数据源 |
|------|------|------|--------|
| Day 1 Retention | 注册次日回访% | >50% | DAU |
| Day 7 Retention | 注册第 7 天回访% | >30% | DAU |
| Day 30 Retention | 注册第 30 天回访% | >20% | DAU |
| Daily Push Open Rate | iMessage/Telegram/Email 中点击链接% | >25% | Deep link clicks |
| Weekly Active Dashboard | 每周至少 1 次 Dashboard 访问% | >60% (付费用户) | Page views |
| Portfolio NAV Refresh Rate | 每周至少 1 次 portfolio 查看% | >50% (Pro 用户) | Portfolio page views |
| Report Read Rate | 生成报告后实际打开的% | >70% | Report open events |
| Feature Adoption Breadth | 使用 >3 个功能模块的用户% | >40% (付费用户) | Feature usage |

---

## 五、Revenue Metrics（收入）

| 指标 | 定义 | 目标 (Month 1) | 目标 (Month 3) |
|------|------|---------------|---------------|
| MRR (Monthly Recurring Revenue) | 月度经常性收入 | $500 | $3,000 |
| ARPU (Average Revenue Per User) | MRR / 付费用户数 | $29.9 | $50 |
| Free → Pro Conversion | Free 用户转为 Pro% | 5% | 8% |
| Pro → Max Upgrade | Pro 用户升级为 Max% | 10% | 15% |
| Churn Rate | 月度取消订阅% | <5% | <3% |
| Credit Overage | 因信用不足导致的升级% | Track | Optimize |
| Gross Margin by Plan | (收入 - COGS) / 收入 | >80% | >85% |
| LTV (Lifetime Value) | ARPU / Churn Rate | >$600 | >$1,600 |
| LTV/CAC Ratio | LTV / CAC | >3x | >5x |

### COGS 估算

| 成本项 | 每用户/月 | 说明 |
|--------|----------|------|
| LLM API (OpenAI) | $0.50 – $2.00 | 取决于调用频率和 model |
| Market Data API | $0.10 – $1.00 | CoinGecko/X API |
| iMessage Relay infra | $0.50 – $2.00 | Mac mini hosting |
| Cloud hosting | $1.00 – $3.00 | API + DB + Redis |
| **Total COGS/user** | **$2 – $8** | |

---

## 六、Quality Metrics（质量）

| 指标 | 定义 | 目标 | 数据源 |
|------|------|------|--------|
| Report Helpfulness Score | 用户对报告的评分 (1-5) | >4.0 | In-app rating |
| Signal Accuracy Feedback | 用户标记 "helpful" 的信号% | >60% | Signal feedback |
| Hallucination Report Rate | 用户报告内容错误的次数 | <1% of reports | User reports |
| Stale Data Rate | 数据显示 stale 标记的时间% | <5% | Data freshness check |
| Failed Notification Rate | 推送失败的% | <2% | NotificationDelivery |
| iMessage Delivery Success | iMessage 发送成功率 | >95% | NotificationDelivery |
| API Error Rate | 5xx 错误 / 总请求 | <1% | Server logs |
| API Latency (p95) | 95 分位响应时间 | <2s | Server logs |
| Dashboard Load Time (p95) | 前端页面加载时间 | <3s | RUM |

---

## 七、Referral Metrics（推荐）

| 指标 | 定义 | 目标 |
|------|------|------|
| NPS (Net Promoter Score) | 推荐可能性评分 | >30 |
| Referral Rate | 通过推荐链接注册的用户% | >10% (Month 3+) |
| Viral Coefficient | 每个用户带来的新用户数 | >0.2 |

---

## 八、仪表盘和监控

### 日常监控 (Real-time)
- API error rate > 1% → Alert
- Stripe webhook failure → Alert
- iMessage relay health → Alert
- DB connection pool exhaustion → Alert

### 周度回顾 (Weekly)
- Activation rate
- Retention rate
- MRR growth
- New paying users
- Churned users

### 月度回顾 (Monthly)
- Full funnel analysis
- Cohort retention
- Plan distribution
- Feature adoption
- Cost analysis

---

## 九、关键产品决策指标

| 决策 | 关键指标 | 阈值 |
|------|---------|------|
| 是否增加 Free 信用额度 | Free→Pro conversion rate | <3% → 增加 |
| 是否提价 | LTV/CAC ratio | >5x → 可提价 |
| 是否砍掉某功能 | Feature adoption | <10% → 考虑砍掉 |
| 是否投广告 | CAC < LTV/3 | CAC <$200 → 可投放 |
| 是否需要 mobile app | Mobile web usage | >40% → 考虑 native app |
