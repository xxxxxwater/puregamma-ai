# PureGamma AI — 用户画像 (User Personas)

**版本**: v1.0  
**日期**: 2026-07-06

---

## Persona 1: Crypto Active Investor（加密活跃投资者）

### 画像
| 维度 | 描述 |
|------|------|
| 姓名 | Alex, 34 |
| 职业 | Tech 公司工程师 |
| 投资经验 | 3-5 年 crypto |
| AUM | $50K – $200K |
| 持仓 | BTC/ETH/SOL + 5-10 山寨币 |
| 设备 | iPhone + MacBook |

### 痛点
- 每天早上花 45 分钟刷 Twitter/Discord/Telegram 获取信息
- KOL 信息互相矛盾，不知道信谁
- 没有系统性的研究框架，凭感觉交易
- 同时在 5 个 app 之间切换（TradingView、CoinGecko、Twitter、Discord、Telegram）

### 为什么不用 ChatGPT 就够了？
- ChatGPT 不追踪 portfolio，不能告诉我"你的仓位现在风险如何"
- ChatGPT 没有实时 market data
- ChatGPT 不能每天早上主动推送到 iMessage
- ChatGPT 不能融合 KOL sentiment + on-chain data + macro

### 为什么需要每日 iMessage？
- 早晨起床第一件事看手机
- 不需要打开 app → 降低使用门槛
- iMessage 是最高优先级的通知渠道
- "60 秒读完"符合忙碌工程师的时间预算

### 支付意愿
- $29.9/mo (Pro) — 愿意
- $199/mo (Max) — 需要看到明确价值（X KOL + on-chain）

### 最关心的指标
1. BTC 统治力与山寨币轮动
2. 资金费率是否过热
3. KOL 情绪是否极端
4. 自己的持仓风险评分

### 风险/合规/隐私顾虑
- 不想分享持仓细节给第三方
- 不想收到"买卖信号"（怕法律问题）
- 数据安全：API key 如何存储

### Activation Moment
**首次收到 iMessage Brief 并打开 Dashboard 查看完整报告**

### Retention Driver
**每日早晨 8:00 准时收到 iMessage，成为晨间仪式**

### Churn 原因
- iMessage 推送不准时或内容质量低
- 信用额度不够用
- 信号与现实不符（hallucination）
- 没有 portfolio 集成（研究与我无关）

---

## Persona 2: Crypto Fund / Small Family Office（小型加密基金 / 家族办公室）

### 画像
| 维度 | 描述 |
|------|------|
| 姓名 | Sarah, 42 |
| 职业 | Family Office 合伙人 |
| 投资经验 | 10 年 TradFi + 4 年 crypto |
| AUM | $1M – $5M |
| 持仓 | BTC/ETH + MSTR/IBIT + 结构化产品 |
| 团队 | 2-3 人 |
| 设备 | iPhone + Mac + iPad |

### 痛点
- Bloomberg Terminal 太贵（$2,500/mo/seat）
- 需要向客户/家族成员汇报 portfolio 状况
- 需要系统化的研究记录（合规要求）
- 需要同时追踪 crypto + equity proxy（MSTR/IBIT/STRC）

### 为什么不用 ChatGPT 就够了？
- ChatGPT 不能生成可审计的研究报告
- ChatGPT 不能追踪跨资产 portfolio
- ChatGPT 不能做策略回测

### 为什么需要每日 iMessage？
- 投资委员会会议前快速 overview
- 团队成员可以同时接收
- 紧急风险提醒（drawdown alert）

### 支付意愿
- $199/mo (Max) — 合理
- Enterprise — 如果需要 Bloomberg adapter + private deployment

### 最关心的指标
1. Portfolio NAV + Daily PnL
2. 跨资产相关性分析
3. Drawdown risk
4. Strategy backtest 结果
5. 合规文档（研究报告存档）

### 风险/合规/隐私顾虑
- 必须能导出 PDF 报告供审计
- 持仓数据不得泄露
- 所有研究必须标注 disclaimer
- 需要 private deployment 选项

### Activation Moment
**完成 Portfolio 同步 + 生成第一份 Portfolio-Aware Brief + 团队都收到 iMessage**

### Retention Driver
**每日 iMessage + 每周 Portfolio NAV 报告 + 策略回测结果**

### Churn 原因
- 数据不准确导致决策失误
- 无法整合 Bloomberg 数据（如果他们用 Bloomberg）
- 合规/安全审查不通过
- 价格 vs Bloomberg 不具吸引力

---

## Persona 3: High-Net-Worth Retail Investor（高净值零售投资者）

### 画像
| 维度 | 描述 |
|------|------|
| 姓名 | Michael, 48 |
| 职业 | 企业家 / 前金融从业者 |
| 投资经验 | 20 年投资 + 5 年 crypto |
| AUM | $500K – $2M |
| 持仓 | BTC/ETH + 美股 + IBIT |
| 设备 | iPhone + iPad |

### 痛点
- 不想花时间做研究，但也不想完全被动
- 需要"可信的第二意见"
- 现有工具要么太复杂（Bloomberg）要么太浅（CoinMarketCap）
- 需要 portfolio 级别的风险评估

### 为什么不用 ChatGPT 就够了？
- 需要结构化输出，不是对话
- 需要 portfolio-aware：我的持仓风险怎么样？
- 需要每天早上主动推送，不是自己去问

### 为什么需要每日 iMessage？
- 简洁、优雅、不侵入
- 像读早报一样的仪式感
- 不需要登录网页

### 支付意愿
- $199/mo (Max) — 没问题（对比私人银行研究报告 $500+/mo）
- Enterprise — 如果需要定制报告

### 最关心的指标
1. Portfolio 总回报 vs BTC benchmark
2. 风险敞口
3. 市场情绪概览
4. 策略建议（非交易建议）

### 风险/合规/隐私顾虑
- 极度重视隐私
- 不希望数据被用于训练模型
- 需要明确的免责声明

### Activation Moment
**首次收到包含 portfolio 评分的 iMessage Brief**

### Retention Driver
**每周 Portfolio NAV 摘要 + 月度策略回顾**

### Churn 原因
- 内容质量不达预期
- 隐私顾虑未解决
- 替代方案出现

---

## Persona 4: Quant / Systematic Trader（量化 / 系统化交易者）

### 画像
| 维度 | 描述 |
|------|------|
| 姓名 | David, 29 |
| 职业 | 独立量化研究员 |
| 投资经验 | 5 年 crypto quant |
| AUM | $100K – $500K |
| 持仓 | 多资产策略组合 |
| 设备 | Mac + 多台服务器 |

### 痛点
- 需要快速验证策略想法
- NautilusTrader 配置复杂，想要开箱即用的回测
- 需要多数据源融合的信号
- 想要对比自己的策略 vs 参考策略

### 为什么不用 ChatGPT 就够了？
- 需要回测功能（ChatGPT 不能做）
- 需要定量输出（Sharpe / drawdown / win rate）
- 需要多数据源自动化

### 为什么需要每日 iMessage？
- 信号触发时的即时通知
- 策略回测完成的推送
- Market regime 变化提醒

### 支付意愿
- $199/mo (Max) — 愿意（对比自建 infra 成本）
- Enterprise — 如果需要 custom data source + API access

### 最关心的指标
1. Sharpe ratio / max drawdown / win rate
2. Signal confidence distribution
3. Market regime classification accuracy
4. Backtest speed & reliability
5. Data source latency

### 风险/合规/隐私顾虑
- 策略 IP 保护
- 不会自动执行交易
- 数据质量要求极高

### Activation Moment
**完成第一个 backtest 并获得可比较的 metrics**

### Retention Driver
**策略实验室的持续使用 + Market regime 信号更新**

### Churn 原因
- 回测数据不准确
- 策略表现不如预期
- 无法自定义数据源
