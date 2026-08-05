# PureGamma AI — MVP 上线清单

**版本**: v1.0  
**日期**: 2026-07-06

---

## 上线标准

每个模块必须满足 "Ready for Production" 标准才能上线。

---

## 一、产品体验标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| P1 | Landing page 清晰传达产品价值，CTA 可点击 | ✅ 已有 | — |
| P2 | Onboarding 流程完整（3 步），用户可在 2 分钟内完成 | ❌ 不存在 | **BLOCKER** |
| P3 | Dashboard 首次加载显示完整内容（非空状态） | ✅ 已有 | — |
| P4 | 所有页面有 Loading / Empty / Error 三种状态 | ⚠️ 部分 | HIGH |
| P5 | 所有页面有响应式设计（Desktop + Mobile） | ⚠️ 部分 | MEDIUM |
| P6 | 所有 CTA 按钮有明确的点击反馈 | ✅ 已有 | — |
| P7 | 所有研究内容包含 "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content." | ⚠️ 部分 | **BLOCKER** |
| P8 | 所有错误信息对用户友好（不暴露技术细节） | ⚠️ 部分 | HIGH |

---

## 二、计费标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| B1 | Stripe Checkout 流程端到端可用 | ⚠️ Mock only | HIGH |
| B2 | Webhook 签名验证正确 | ✅ | — |
| B3 | 重复事件不双重发放信用额度 | ⚠️ 仅 event-id 去重 | **BLOCKER** |
| B4 | 订阅取消后正确降级到 Free | ✅ | — |
| B5 | 支付失败后限制高成本功能 | ✅ | — |
| B6 | Credit 消耗有 `SELECT FOR UPDATE` | ❌ 不存在 | **BLOCKER** |
| B7 | Credit 历史可追溯（CreditLedger） | ✅ | — |
| B8 | Credit 不足时返回 402 + 明确提示 | ✅ | — |
| B9 | 升级/降级逻辑正确（不丢失数据） | ✅ | — |
| B10 | Mock mode 和 Production mode 切换正确 | ⚠️ | HIGH |

---

## 三、iMessage 推送标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| I1 | iMessage relay 认证安全（非默认密钥） | ❌ | **BLOCKER** |
| I2 | 消息 idempotency 正确（不重复发送） | ✅ | — |
| I3 | 消息长度检查（双边） | ✅ | — |
| I4 | Rate limit 有效（20/天/用户） | ✅ | — |
| I5 | 发送失败时 credit 退还 | ❌ | **BLOCKER** |
| I6 | Disclaimer 出现在每条消息末尾 | ⚠️ | **BLOCKER** |
| I7 | 消息内容不泄露敏感信息 | ✅ | — |
| I8 | 仅 Max/Enterprise 用户可收到 iMessage | ✅ | — |
| I9 | Fallback 到 Email（relay 不可达时） | ❌ | HIGH |

---

## 四、Portfolio NAV 标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| N1 | 手动持仓输入可用 | ❌ | HIGH (Pro 核心) |
| N2 | NAV 计算正确（不重复计算） | ❌ | — |
| N3 | PnL 计算正确 | ❌ | — |
| N4 | 用户 A 不能看到用户 B 的 portfolio | ⚠️ API 已检查 | — |
| N5 | Portfolio 数据变化时显示 freshness 标记 | ❌ | MEDIUM |

---

## 五、数据管道标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| D1 | 至少 1 个数据源有真实数据（非 mock） | ❌ | HIGH |
| D2 | 数据去重（不重复写入 MarketSnapshot） | ❌ | MEDIUM |
| D3 | Stale data 检测和标记 | ❌ | MEDIUM |
| D4 | 数据源状态页正确反映连接状态 | ✅ | — |
| D5 | Mock/Real 隔离（生产不误用 mock） | ⚠️ | HIGH |

---

## 六、安全标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| S1 | JWT 认证（非 header-based） | ❌ | **BLOCKER** |
| S2 | Admin 端点有严格权限校验 | ⚠️ role check | **BLOCKER** |
| S3 | 用户 A 不能访问用户 B 的数据 | ⚠️ 部分 | **BLOCKER** |
| S4 | API key 不暴露在日志/响应中 | ⚠️ | HIGH |
| S5 | HTTPS 强制 | ⚠️ | HIGH |
| S6 | Rate limiting on public endpoints | ❌ | HIGH |
| S7 | SQL injection 防护（使用 ORM） | ✅ | — |
| S8 | CORS 配置正确 | ✅ | — |

---

## 七、合规标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| C1 | 所有研究和信号标注 "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content." | ⚠️ 部分 | **BLOCKER** |
| C2 | 无自动交易功能 | ✅ | — |
| C3 | 不托管用户资金 | ✅ | — |
| C4 | Privacy Policy 页面 | ❌ | **BLOCKER** |
| C5 | Terms of Service 页面 | ❌ | **BLOCKER** |
| C6 | 用户可请求数据删除 | ❌ | HIGH (GDPR) |
| C7 | Cookie consent（如适用） | ❌ | MEDIUM |

---

## 八、文档标准

| # | 标准 | 状态 | 优先级 |
|---|------|------|--------|
| O1 | PRD | ✅ 已创建 | — |
| O2 | MVP Scope | ✅ 已创建 | — |
| O3 | User Personas | ✅ 已创建 | — |
| O4 | User Journey | ✅ 已创建 | — |
| O5 | SaaS Plans | ✅ 已创建 | — |
| O6 | iMessage Brief Spec | ✅ 已创建 | — |
| O7 | Product Roadmap | ✅ 已创建 | — |
| O8 | Launch Checklist | ✅ 本文档 | — |
| O9 | Metrics | ✅ 已创建 | — |
| O10 | Backlog | ✅ 已创建 | — |
| O11 | API Documentation | ❌ | HIGH |
| O12 | Self-host README | ✅ | — |

---

## 九、阻塞项汇总

上线前必须解决的 **BLOCKER** 清单：

| # | 问题 | 文件 | 修复工作量 |
|---|------|------|-----------|
| 1 | 无 JWT 认证 | dependencies.py | 3-5 天 |
| 2 | Admin 越权 | auth.py:42 | 1 行 |
| 3 | Credit 竞态条件 | credit_service.py | 1 行 (with_for_update) |
| 4 | Invoice 双重发放信用 | billing_service.py | 5-10 行 |
| 5 | iMessage relay 默认密钥 | imessage-relay/config.py | 1 行 |
| 6 | 消息发送失败不退 credit | dispatcher.py | 3-5 行 |
| 7 | Disclaimer 缺失部分端点 | 多处 | 全局检查 |
| 8 | Privacy / ToS 页面不存在 | web/ | 2 页面 |
| 9 | Onboarding 流程不存在 | web/ | 3 页面 |
| 10 | 无真实数据源 | data/ | 1-2 周 |

---

## 九（续）. 产品功能 BLOCKER（来自 PM Gap 分析）

| # | 问题 | 优先级 | 修复方向 |
|---|------|--------|---------|
| 11 | Onboarding flow 缺失 — 用户从注册到首次 Daily Brief 无引导 | 🔴 BLOCKER | 创建 3 步 onboarding |
| 12 | iMessage 内容过于简单 — 当前只发 "report is ready" | 🔴 BLOCKER | 实现 fused brief 模板 |
| 13 | Portfolio-aware report 缺失 — 当前 daily report 是通用版 | 🔴 BLOCKER | 基于 preferred_assets 个性化 |
| 14 | 用户偏好设置不完整 — 缺少推送时间、研究风格选择 | 🟡 HIGH | 补充 UserPreference 字段 |
| 15 | CoinGecko 真实数据未接入 — 全部 mock | 🟡 HIGH | 接入 CoinGecko 免费 API |
| 16 | Daily push 时间不可配 — 固定 UTC 00:20 | 🟡 MEDIUM | 添加用户时区 + 时间设置 |

---

## 十、上线就绪判定

| 类别 | 状态 | BLOCKER 数 |
|------|------|-----------|
| 安全 | ❌ | 6 |
| 计费 | ❌ | 2 |
| 推送 | ❌ | 3 |
| 合规 | ❌ | 2 |
| 产品体验 | ❌ | 4 (含新增 3 个) |

**总体判定**: **未就绪。** 需要解决 17 个 BLOCKER（10 个原有 + 3 个产品功能 + 4 个与原有重叠更新）后进入 Beta，再经过 2-4 周 Beta 测试后正式上线。

### 预计上线时间线

```
Week 1-2: 安全 + 计费 BLOCKER（10 个）
Week 3-4: 产品体验 BLOCKER（Onboarding + iMessage 模板 + Portfolio-aware）
Week 5-6: 合规 + 推送 BLOCKER
Week 7-8: CoinGecko 接入 + Beta 用户邀请
Week 9-10: Beta 反馈修复
Week 11:   v1.0 Public Launch 🚀
```

### MVP 上线必须满足的最小条件

1. ✅ 用户能注册/登录（JWT）
2. ✅ 用户能看到 Daily Market Report
3. ✅ Max 用户能收到 iMessage Daily Brief
4. ✅ 用户能通过 Stripe 付费升级
5. ✅ Credit 系统正确计费
6. ✅ 所有输出带 disclaimer
7. ✅ 至少 1 个真实数据源（CoinGecko）
