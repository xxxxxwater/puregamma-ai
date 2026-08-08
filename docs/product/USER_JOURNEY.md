# PureGamma AI — 用户旅程
**版本**: v1.0  
**日期**: 2026-07-06
---
## 旅程概览
```
Landing → Sign Up → Onboarding → Watchlist → Research Style → Channels → First Brief → Push Time → Credits → Upgrade → Portfolio → NAV Brief → Nautilus
```
---
## Step 1: Landing Page
**页面**: `/` (app/page.tsx)
**当前状态**: ✅ 已存在
**用户看到**:
- Hero: "Scientific market intelligence for crypto portfolios."
- 6 个 methodology cards
- CTA: "Open Intelligence Console" / "View Methodology"
**主要 CTA**: Open Intelligence Console → 进入 Dashboard
**成功状态**: 用户点击 CTA 进入
**失败状态**: 用户 bounce（需 A/B test headline）
**升级提示**: 不在此步骤
**合规提示**: 不在此步骤
**Telemetry**: `landing_page_view`, `cta_click`
---
## Step 2: Sign Up / Mock Login
**页面**: `/auth/mock-login` (API) → 无专属前端页面
**当前状态**: ⚠️ 需要创建注册/登录页面
**MVP 行为**:
- 点击 "Open Intelligence Console" → mock login 自动创建 demo 用户
- 设置 Header `X-User-Id` 返回给前端
- **阻塞项**: 需要实现 JWT auth 替代当前的 header-based auth
**主要 CTA**: "Start Free Trial"
**成功状态**: 用户获得 JWT token + 重定向到 Dashboard
**失败状态**: 登录失败提示
**升级提示**: 不在此步骤
**合规提示**: "By continuing, you agree to our Terms. "
**Telemetry**: `signup_start`, `signup_complete`, `signup_error`
**MVP 需要的改进**:
1. 创建 `/app/signup/page.tsx` — 注册页面
2. 创建 `/app/login/page.tsx` — 登录页面  
3. 实现 JWT auth 替代 X-User-Id header
4. 邮箱验证（可选，MVP 可跳过）
---
## Step 3: Onboarding — 选择关注资产
**页面**: 新建 `/app/onboarding/assets/page.tsx`
**当前状态**: ❌ 不存在
**用户看到**:
- "Select assets you want to track"
- 6 个默认资产卡片：BTC、ETH、SOL、HYPE、MSTR、STRC
- 每个卡片显示：名称、类别、简要描述
- 多选 + "Select All"
**默认选中**: BTC、ETH、SOL
**主要 CTA**: "Continue →"
**成功状态**: 选择保存到 UserPreference.preferred_assets
**失败状态**: 未选择任何资产 → 禁用 Continue
**升级提示**: 不在此步骤
**合规提示**: 不在此步骤
**Telemetry**: `onboarding_assets_selected`, `onboarding_step_complete`
---
## Step 4: Onboarding — 选择研究风格
**页面**: 新建 `/app/onboarding/style/page.tsx`
**当前状态**: ❌ 不存在
**用户看到**:
- "Choose your research style"
- 5 个选项卡片：
  1. **Event-Driven** — "I trade based on catalysts and news events"
  2. **Momentum** — "I follow trends and price momentum"
  3. **Macro-Sensitive** — "I care about macro and rates"
  4. **High Beta** — "I seek high-risk, high-reward setups"
  5. **Risk-Controlled** — "I prioritize capital preservation"
**单选**（默认：Risk-Controlled）
**主要 CTA**: "Continue →"
**成功状态**: 选择保存到 UserPreference.preferred_style
**失败状态**: 未选择 → 禁用 Continue
**升级提示**: 不在此步骤
**合规提示**: "Your style preference affects report emphasis, not trade recommendations."
**Telemetry**: `onboarding_style_selected`
---
## Step 5: Onboarding — 连接通知渠道
**页面**: 新建 `/app/onboarding/channels/page.tsx`
**当前状态**: ❌ 不存在
**用户看到**:
- "How would you like to receive research?"
- 3 个渠道卡片：
  1. **iMessage** — 输入电话号码（仅 Max 可见）
  2. **Telegram** — 输入 chat ID 或扫码
  3. **Email** — 预填注册邮箱
**主要 CTA**: "Complete Setup →"
**成功状态**: 渠道配置保存到 UserPreference
**失败状态**: 无渠道选择 → 仍然可跳过
**升级提示**: iMessage 卡片显示 "Max plan required" 灰色锁定状态
**合规提示**: "We will never share your contact information."
**Telemetry**: `onboarding_channels_selected`
---
## Step 6: 生成第一份 Daily Brief
**页面**: 重定向到 `/dashboard`
**当前状态**: ✅ 已存在但需优化
**用户看到**:
- Dashboard 自动调用 `POST /reports/daily` 生成第一份报告
- Loading state: "Generating your first research brief..."
- 成功后显示：Market Regime Banner + 资产卡片 + 信号表格 + 报告内容
**主要 CTA**: "Open Full Report"
**成功状态**: 报告生成成功，Dashboard 完整展示
**失败状态**: 报告生成失败 → "Research engine is warming up. Try again."
**升级提示**: 信用剩余显示在顶部状态栏
**合规提示**: "" 在报告底部
**Telemetry**: `first_report_generated`, `dashboard_view`, `report_open`
---
## Step 7: 设置每日推送时间
**页面**: `/daily-push`
**当前状态**: ⚠️ 前端页面存在但功能需完善
**用户看到**:
- "Daily Push Settings"
- 时间选择器：默认 08:00 UTC / 用户本地时间
- 渠道 toggle：Email / Telegram / iMessage（取决于 plan）
- 内容类型：Market Brief / Portfolio Brief / Combined
**主要 CTA**: "Save Push Settings"
**成功状态**: 设置保存 + "You'll receive your first brief tomorrow at 08:00"
**失败状态**: 时间格式错误
**升级提示**: "iMessage push requires Max plan" / "Portfolio brief requires Pro plan"
**合规提示**: "Push messages include mandatory disclaimer."
**Telemetry**: `push_settings_saved`, `push_channel_enabled`
---
## Step 8: 看到信用消耗
**页面**: `/billing`
**当前状态**: ✅ 已存在
**用户看到**:
- 当前 Plan + Subscription Status
- Credit Balance（大数字）
- Credit Usage Chart（近 8 次操作）
- 使用历史表格（Action / Delta / Balance After / Time）
- 4 个 Plan 卡片 + 升级按钮
**主要 CTA**: "Upgrade to Pro" / "Upgrade to Max"
**成功状态**: 用户理解信用模型
**升级提示**: 当信用余额 < 100 时，顶部显示黄色 banner "Running low on credits"
**合规提示**: 不在此步骤
**Telemetry**: `billing_page_view`, `credit_balance_check`
---
## Step 9: 升级 Max
**页面**: `/billing` → Stripe Checkout
**当前状态**: ✅ 已存在
**用户旅程**:
1. 点击 "Upgrade to Max"
2. 跳转 Stripe Checkout (production) 或 mock checkout (dev)
3. 完成支付
4. 重定向到 `/billing/success`
5. Webhook 触发：update subscription + grant credits
6. iMessage 渠道自动解锁
**主要 CTA**: "Upgrade to Max"
**成功状态**: Plan 变更为 Max + iMessage 解锁
**失败状态**: 支付失败 → `/billing/cancel`
**升级提示**: 不在此步骤（用户已经在升级）
**合规提示**: 不在此步骤
**Telemetry**: `upgrade_initiated`, `upgrade_completed`, `upgrade_failed`
---
## Step 10: 连接 Plaid / CEX / Wallet
**页面**: `/integrations`
**当前状态**: ⚠️ 前端页面存在但功能需实现
**MVP 阶段**: 此步骤仅对 Pro+ 用户可见，且仅提供手动持仓输入。
**自动同步（Plaid/CEX/Wallet）推迟到 3-6 个月后。**
**用户看到（MVP）**:
- "Connect Your Portfolio"
- 手动输入表单：Asset + Quantity + Cost Basis
- 或上传 CSV
**用户看到（Later）**:
- Plaid "Connect Brokerage" 按钮
- Binance/Coinbase "Connect Exchange (Read-Only)" 按钮
- Wallet Address 输入框
**主要 CTA**: "Save Portfolio"
**成功状态**: Portfolio 数据保存 + NAV 计算
**失败状态**: 连接失败 / API key 无效
**升级提示**: "Auto-sync requires Pro plan" / "CEX sync requires Max plan"
**合规提示**: "We only request read-only access. Your funds remain in your control."
**Telemetry**: `integration_connected`, `portfolio_synced`
---
## Step 11: 生成 Portfolio NAV Brief
**页面**: `/portfolio`
**当前状态**: ⚠️ 前端存在但 backend 无实现
**MVP 阶段**: 仅手动持仓 + NAV 计算。
**自动 NAV 推迟到 3-6 个月后。**
**用户看到**:
- Total NAV + Daily PnL
- Cash/Crypto/Equity 敞口
- Drawdown estimate
- NAV 历史图
- 持仓明细表
- 风险指标卡片
**主要 CTA**: "Generate Portfolio Brief"
**成功状态**: Portfolio-Aware Report 生成
**失败状态**: 无持仓数据 → "Add positions to generate portfolio analysis"
**升级提示**: "Auto-sync from Plaid/CEX requires Pro/Max plan"
**合规提示**: "Portfolio data is processed locally. "
**Telemetry**: `portfolio_page_view`, `portfolio_brief_generated`
---
## Step 12: 查看 Nautilus Backtest
**页面**: `/nautilus`
**当前状态**: ⚠️ 前端存在但 backend 无实现
**MVP 阶段**: 使用 mock backtest engine。
**真实 NautilusTrader 集成推迟到 3-6 个月后。**
**用户看到**:
- Strategy 选择器（6 个预定义策略）
- Backtest 参数输入
- 结果展示：Sharpe / Drawdown / Win Rate / Total Return
- Disclaimer: "Live trading is disabled by default."
**主要 CTA**: "Run Backtest"
**成功状态**: Backtest 完成 + 结果展示
**失败状态**: 参数无效 / 信用不足
**升级提示**: "Advanced backtest requires Max plan"
**合规提示**: "This is simulated research, not live trading. Past results do not guarantee future performance."
**Telemetry**: `backtest_run`, `backtest_completed`
---
## Step 13: 持续使用 — 每日循环
**不涉及新页面，这是用户的 Daily Loop**:
```
08:00 → 收到 iMessage Brief（Max 用户）
       ↓
08:00 → 收到 Telegram/Email Brief（Pro 用户）
       ↓
用户打开链接 → Dashboard 查看完整报告
       ↓
用户查看 Signals → 了解新的研究信号
       ↓
用户查看 Portfolio → 了解仓位风险
       ↓
用户运行 Backtest → 验证策略想法
       ↓
第二天 08:00 → 循环
```
---
## 旅程中的关键情绪点
| 步骤 | 用户情绪 | 风险 |
|------|---------|------|
| Landing | 好奇 | Bounce |
| Sign Up | 犹豫 | Abandon |
| Onboarding | 期待 | Drop off |
| First Brief | **兴奋** | 内容质量低 |
| Push Setup | 满意 | 复杂度过高 |
| Credit 见底 | 焦虑 | Churn |
| 升级 | 犹豫 | Price objection |
| Portfolio 同步 | 信任 | 安全顾虑 |
| NAV Brief | **满足** | 数据不准 |
| Nautilus | 探索 | 不理解 |
| 每日循环 | 习惯 | 内容疲劳 |
---
## 用户旅程所需的新页面
MVP 需要新增：
| 页面 | 路由 | 优先级 |
|------|------|--------|
| Sign Up | `/signup` | P0 |
| Login | `/login` | P0 |
| Onboarding — Assets | `/onboarding/assets` | P0 |
| Onboarding — Style | `/onboarding/style` | P0 |
| Onboarding — Channels | `/onboarding/channels` | P0 |
| Settings / Profile | `/settings` | P1 |
已存在但需完善的页面：
| 页面 | 路由 | 需完善 |
|------|------|--------|
| Daily Push | `/daily-push` | 后端 API + 时间选择器 |
| Integrations | `/integrations` | 手动持仓输入表单 |
| Portfolio | `/portfolio` | 后端 NAV 计算 API |
| Nautilus | `/nautilus` | 后端回测 API |
