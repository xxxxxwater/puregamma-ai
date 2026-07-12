# PureGamma AI — 每日 iMessage Brief 产品规格

**版本**: v1.0  
**日期**: 2026-07-06  
**状态**: 核心功能规格

---

## 1. 产品定位

每日 iMessage Brief 是 PureGamma AI 的**核心留存功能**。它不是"另一个推送通知"，而是用户的**晨间研究仪式**——像读早报一样，在 60 秒内完成市场概览。

---

## 2. 设计原则

1. **60 秒可读完**：消息长度上限 3,000 字符，实际控制在 800-1,500 字符
2. **Push > Pull**：用户不需要打开 app 即可获取关键信息
3. **可操作性**：每条 Brief 包含一个深度阅读链接
4. **一致性**：每天同一时间到达，结构一致
5. **非侵入**：不会频繁推送，每天 1 条（除非极端风险事件）
6. **合规优先**：每条消息末尾必须有 disclaimer

---

## 3. 发送时间

- **默认时间**: 每天 08:00 UTC（用户可自定义）
- **时区感知**: 基于用户设置的时区调整
- **发送窗口**: 06:00 – 10:00 用户本地时间
- **延迟处理**: 如果数据 pipeline 延迟 > 30 分钟，发送 "Delayed Brief" 标识

---

## 4. 消息模板

### 4.1 Market-Only Brief（纯市场简报）

适用于：没有连接 portfolio 的用户

```
PureGamma AI Daily Crypto Brief — {date}

Market Regime:
{market_regime_summary}

Top Signals:
1. {signal_1}
2. {signal_2}
3. {signal_3}

Risk:
{risk_one_liner}

Data Freshness: {freshness_indicator}

Open Dashboard → {dashboard_deep_link}

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

### 4.2 Portfolio-Only Brief（纯组合简报）

适用于：已连接 portfolio 的用户

```
PureGamma AI Portfolio Brief — {date}

NAV: ${total_nav} | Daily: {pnl_change}

Allocation:
Crypto: {crypto_pct}% | Equity: {equity_pct}% | Cash: {cash_pct}%

Risk:
Drawdown est: {drawdown_est} | BTC beta: {beta}

Top Movers:
{top_movers_list}

View Portfolio → {portfolio_deep_link}

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

### 4.3 Combined Brief（市场 + 组合）

适用于：Max 用户，同时关注市场和组合

```
PureGamma AI Daily Brief — {date}

Market: {regime_one_liner}
Portfolio: ${nav} {pnl_emoji} {pnl_pct}%

Key Signal: {top_signal}
Risk Level: {risk_level}

View Full Report → {dashboard_deep_link}

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

---

## 5. 消息最大长度

| 类型 | 最大长度 | 实际目标 |
|------|---------|---------|
| Market Brief | 3,000 chars | 1,200 chars |
| Portfolio Brief | 3,000 chars | 800 chars |
| Combined | 3,000 chars | 600 chars |
| Risk Alert | 3,000 chars | 400 chars |

---

## 6. 内容禁止规则

以下内容**绝对不能**出现在 iMessage Brief 中：

1. ❌ 买卖建议（"Buy BTC now"、"Sell ETH"）
2. ❌ 价格目标（"BTC will reach $150K"）
3. ❌ 保证收益（"This strategy returns 20%"）
4. ❌ 个人投资建议（"You should..."）
5. ❌ 恐慌性语言（"CRASH"、"PANIC"、"DUMP"）
6. ❌ 具体持仓数量（"You hold 2.5 BTC"）
7. ❌ API key 或敏感信息
8. ❌ 外部链接（除 PureGamma dashboard 链接外）

---

## 7. Partial Data 处理

| 场景 | 处理方式 |
|------|---------|
| Market data 延迟 > 5 分钟 | 显示 "Delayed data" 标记 |
| X KOL 数据不可用 | 跳过 KOL 模块，不显示 |
| On-chain 数据不可用 | 跳过 on-chain 模块 |
| Portfolio 同步失败 | 发送 Market-Only Brief 而不是 Combined |
| 所有数据不可用 | 发送简短消息 "Research engine is updating. Brief will resume shortly." |

---

## 8. Stale Data 处理

| 数据源 | Stale Threshold | 行为 |
|--------|----------------|------|
| Market Quote | 5 分钟 | 显示 "Market data delayed X min" |
| X KOL | 30 分钟 | 显示 "Sentiment data from X min ago" |
| On-chain | 1 小时 | 显示 "On-chain data may be stale" |
| Portfolio NAV | 1 小时 | 显示 "NAV as of HH:MM UTC" |

如果关键数据（market quote）stale 超过 15 分钟，不发送 Brief。

---

## 9. Disclaimer 格式

每条 iMessage 必须以以下格式结尾（不可省略）：

```
---
Users bear all risks of using this service. The service provider is not responsible for any AI-generated content. PureGamma AI provides research tools, not investment recommendations. Past performance does not guarantee future results.
```

或者精简版：

```
Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

**精简版适用于空间不足时。**

---

## 10. Dashboard 唤起机制

每条 Brief 包含 ONE deep link：

```
Open Dashboard → https://puregamma.ai/dashboard
View Portfolio → https://puregamma.ai/portfolio
View Signal   → https://puregamma.ai/signals/{signal_id}
```

**链接必须是 ONE — 避免选择疲劳。** 优先级：
1. Combined Brief → Dashboard
2. Market Brief → 当日报告
3. Portfolio Brief → Portfolio 页面
4. Risk Alert → Dashboard

---

## 11. 防 Spam 策略

为避免用户觉得是 spam：

1. **频率**: 每天最多 1 条常规 Brief
2. **极端事件**: 每周最多 2 条额外 Risk Alert
3. **静音**: 支持在 `/daily-push` 设置 "Weekend off"
4. **退订**: 每条消息末尾包含 "Reply STOP to unsubscribe"
5. **频率回调**: 如果用户连续 7 天未打开 Dashboard link → 降频至每 2 天

---

## 12. 发送成本控制

| 策略 | 说明 |
|------|------|
| Credit 消耗 | iMessage 每条 3 credits（比 Telegram 贵 3x，反映 relay 成本）|
| Rate Limit | 每用户每天最多 20 条 iMessage（包括 Brief + Alert）|
| 批量发送 | Celery worker 串行发送，避免并发 relay 瓶颈 |
| Relay 健康检查 | 发送前检查 relay `/health`，失败则 fallback 到 Email |

---

## 13. 发送失败处理

| 失败原因 | 行为 | 用户通知 |
|---------|------|---------|
| Relay 不可达 | Fallback 到 Email | "iMessage unavailable. Brief sent via email." |
| 收件人无效 | 标记 channel=skipped | 无 iMessage，静默跳过 |
| 信用不足 | 跳过发送 | Web Dashboard 提示 "Add credits to resume iMessage" |
| 消息过长 | 截断 + "..." | 无特殊通知 |
| 网络超时 | Retry 3 次 | 3 次失败后 fallback Email |

---

## 14. 高质量示例

### 示例 1: 普通 Market Regime 日

```
PureGamma AI Daily Crypto Brief — Jul 6, 2026

Market Regime: Risk-on momentum with contained leverage.
BTC leads, ETH/SOL participating, HYPE elevated.

Top Signals:
1. BTC momentum breakout (confidence 68%, risk 46)
2. ETH/BTC rotation setup (confidence 61%, risk 52)
3. HYPE trend continuation (confidence 55%, risk 71)

Risk: Moderate. Favor liquid assets with explicit invalidation levels.

Data Freshness: Fresh <60s | Mock mode

Open Dashboard → https://puregamma.ai/dashboard

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

### 示例 2: 高波动风险日

```
PureGamma AI Daily Crypto Brief — Jul 6, 2026

Market Regime: Crowded leverage risk. Funding elevated across majors.
Liquidation clusters visible. Reduce size.

Top Signals:
1. BTC elevated funding (risk 78)
2. HYPE overheated (risk 85)
3. DeFi leverage spike

Risk: ELEVATED. Reduce position size and demand confirmation.
Avoid adding to winners until funding resets.

Open Dashboard → https://puregamma.ai/dashboard

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

### 示例 3: Portfolio Drawdown 日

```
PureGamma AI Portfolio Brief — Jul 6, 2026

NAV: $1,284,200 | Daily: -$32,400 (-2.46%)

Allocation:
Crypto: 68% | Equity: 18% | Cash: 14%

Risk: BTC beta 0.74. MSTR proxy exposure elevated.
Concentration in HYPE (22% of crypto) is driving drawdown.

Top Movers:
▼ HYPE -8.2% | ▼ SOL -3.1% | ▲ STRC +1.4%

View Portfolio → https://puregamma.ai/portfolio

Users bear all risks of using this service. The service provider is not responsible for any AI-generated content.
```

---

## 15. 技术实现要点

### 发送流程
```
APScheduler (08:00 UTC)
  → Celery Task: generate_shared_daily_market_intelligence
  → Celery Task: generate_personalized_daily_reports
  → Celery Task: send_daily_reports_to_channels
    → For each Max user with iMessage enabled:
      → Build iMessage Brief from template
      → Check credit balance
      → Send via NotificationDispatcher
      → Record NotificationDelivery
```

### 消息构建
```python
def build_imessage_brief(user, market_regime, signals, portfolio_nav=None):
    if portfolio_nav and user.plan in ("Max", "Enterprise"):
        return render_combined_brief(...)
    return render_market_brief(...)
```

### 发送前检查
1. 用户是否订阅 Max 或 Enterprise
2. 用户是否配置了 iMessage 收件人
3. iMessage channel 是否 enabled
4. Credit balance >= 3
5. 今日 iMessage 数量 < 20
6. iMessage relay `/health` 返回 ok
