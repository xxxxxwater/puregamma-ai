# PureGamma.ai — 产品路线图

**版本**: v2.0 — Founder PM Convergence  
**日期**: 2026-07-06

---

## 路线图总览

```
MVP (现在 – 6 周) ──→ Beta (2-4 周) ──→ v1.0 Launch (1 周)
                                            │
                    ┌───────────────────────┘
                    ▼
              v1.1 (1-2 月) ──→ v1.2 (3-4 月) ──→ v2.0 (6 月+)
             Portfolio + 真实数据    X KOL + Nautilus       Enterprise + Platform
```

### 核心决策

| 决策 | 结论 | 理由 |
|------|------|------|
| Portfolio NAV 是 MVP 吗？ | ❌ 不是。Beta 阶段做 Mock | Plaid 审批 4-8 周，不可控 |
| NautilusTrader 是 MVP 吗？ | ❌ 不是。v1.2 做 | Quant 用户不是首批 ICP |
| X KOL 是 MVP 吗？ | ❌ 不是。v1.2 做 | API 成本高，先用 RSS + CryptoPanic |
| iMessage 是 MVP 吗？ | ✅ 是。Max 专属 | 核心留存引擎，没有 iMessage 产品没有护城河 |
| Stripe 是 MVP 吗？ | ✅ 是 | 没有计费就不能收费 |
| Plaid 是 MVP 吗？ | ❌ 不是。v1.1 做 | 依赖外部审批 |

---

## Phase 0: MVP（现在 – 第 6 周）

**目标**: 一个可以演示、可以试用、可以收费的最小产品。

### Week 1-2: Security Foundation
- [ ] 实现 JWT-based 认证（替换 X-User-Id header）
- [ ] 移除 mock-login 的 role 参数
- [ ] 添加 `SELECT FOR UPDATE` 到 credit 操作
- [ ] iMessage relay secret 强制要求（非默认值）
- [ ] Admin 端点添加严格权限校验

### Week 2-3: Core Experience
- [ ] 创建 Onboarding 流程（3 步：Assets / Style / Channels）
- [ ] 完善 Daily Push 设置页面（时间选择器 + toggle）
- [ ] Dashboard 优化（加载状态、空状态、错误状态）
- [ ] 修复 LLM 调用结果丢弃 bug（H1）
- [ ] 修复 credit 扣除时序问题（H2）

### Week 3-4: Billing Polish
- [ ] Stripe webhook 添加 invoice-level idempotency
- [ ] 信用历史页面完善
- [ ] 信用不足提示优化
- [ ] Plan 升级 flow 端到端测试

### Week 4-5: Notification Polish
- [ ] iMessage Brief 模板实现
- [ ] Notification 发送失败退款机制
- [ ] Rate limit 可视化
- [ ] 推送历史页面

### Week 5-6: Launch Prep
- [ ] Landing page 文案优化
- [ ] Pricing page A/B 测试准备
- [ ] 合规文案审查（每条消息的 disclaimer）
- [ ] Load testing（100 并发用户）
- [ ] Security review（OWASP Top 10）

### MVP 交付物
- ✅ Web Dashboard 完整可用
- ✅ 每日市场报告（mock data）
- ✅ iMessage/Telegram/Email 推送
- ✅ Stripe 订阅（mock mode）
- ✅ Credit 计费系统
- ✅ Onboarding 流程
- ✅ JWT Auth

---

## Phase 1: Beta（第 7-10 周）

**目标**: 真实用户试用，收集反馈，修复 bug。

### Week 7-8: Real Data Integration
- [ ] CoinGecko API 接入（替代 mock market data）
- [ ] X API 接入（KOL 情绪扫描）
- [ ] 数据 pipeline 添加去重和缓存

### Week 8-9: Portfolio MVP
- [ ] 手动持仓输入（Web UI + API）
- [ ] NAV 计算（backend）
- [ ] Portfolio page 接通真实数据
- [ ] Portfolio-Aware Daily Brief

### Week 9-10: Beta Launch
- [ ] 邀请 10-20 名 beta 用户
- [ ] 收集反馈 via Intercom/widget
- [ ] 修复 top 10 bugs
- [ ] Analytics 接入（Mixpanel/PostHog）

---

## Phase 2: v1.0 Public Launch（第 11 周）

**目标**: 公开发布，开始收费。

- [ ] Landing page 最终版
- [ ] Stripe production mode 切换
- [ ] 24/7 监控和告警
- [ ] Customer support 流程
- [ ] Launch blog post + social media

**Launch Goal**: 100 注册用户，10 付费用户（Pro/Max）

---

## Phase 3: v1.1（第 12-20 周）

**目标**: 增强 Pro/Max 价值，提高转化率。

- [ ] Glassnode / Coinglass on-chain data 接入
- [ ] NautilusTrader 回测集成（真实数据）
- [ ] Plaid 美股券商接入
- [ ] CEX read-only API 接入（Binance / Coinbase）
- [ ] On-chain wallet 追踪
- [ ] Portfolio NAV 自动聚合
- [ ] Slack 推送完整实现

---

## Phase 4: v1.2（第 21-32 周）

**目标**: 扩展市场，Enterprise 功能。

- [ ] Agent Chat（LLM 对话式研究）
- [ ] Custom KOL 列表
- [ ] Bloomberg 适配器
- [ ] PDF 报告导出
- [ ] Team Workspace
- [ ] Private Deployment 选项
- [ ] API Access for Enterprise

---

## Phase 5: v2.0（6 个月 +）

**目标**: 平台化。

- [ ] 自定义策略编辑器
- [ ] Community strategies marketplace
- [ ] Mobile app (iOS 优先)
- [ ] Multi-language support
- [ ] Institutional compliance features
- [ ] Data API for third-party developers

---

## 路线图风险

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|---------|
| Auth 实现延期 | 低 | 高 | 先用 JWT 最小实现 |
| CoinGecko API 限流 | 中 | 中 | 提前申请 API key + 缓存 |
| X API 政策变化 | 高 | 高 | 准备备选数据源（Reddit/CryptoPanic）|
| Plaid 合规审查周期 | 高 | 中 | 先上线手动持仓 |
| Stripe 真实环境问题 | 中 | 高 | mock mode 充分测试 |
| 用户获取成本高 | 中 | 高 | 内容营销 + KOL 合作 |
