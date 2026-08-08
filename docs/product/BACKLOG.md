# PureGamma AI — 产品 Backlog
**版本**: v1.0  
**日期**: 2026-07-06
---
## 一、安全问题 (P0 — 上线阻塞)
| ID | 标题 | 严重度 | 文件 | 工作量 |
|----|------|--------|------|--------|
| SEC-001 | 实现 JWT 认证替代 X-User-Id header | Critical | dependencies.py | 3-5d |
| SEC-002 | 移除 mock-login 的 role 参数漏洞 | Critical | auth.py:42 | 1h |
| SEC-003 | Admin 端点添加严格权限校验 | Critical | admin.py | 2h |
| SEC-004 | iMessage relay 默认密钥改为必须配置 | Critical | imessage-relay/config.py | 1h |
| SEC-005 | 信号列表端点添加用户隔离 | High | signals.py | 1h |
| SEC-006 | API 添加 rate limiting | High | main.py | 2h |
| SEC-007 | 环境变量敏感信息不记录到日志 | High | 全局 | 4h |
---
## 二、计费问题 (P0 — 上线阻塞)
| ID | 标题 | 严重度 | 文件 | 工作量 |
|----|------|--------|------|--------|
| BILL-001 | Credit 操作添加 `SELECT FOR UPDATE` | Critical | credit_service.py | 1h |
| BILL-002 | Invoice 级别幂等性（防双重发放） | Critical | billing_service.py | 2h |
| BILL-003 | checkout.session.completed 向 Stripe API 确认状态 | High | billing_service.py | 2h |
| BILL-004 | Stripe production mode 端到端测试 | High | stripe_webhook.py | 1d |
| BILL-005 | 移除 subscription_update 的全额信用发放 | Medium | billing_service.py | 1h |
---
## 三、推送问题 (P0 — 上线阻塞)
| ID | 标题 | 严重度 | 文件 | 工作量 |
|----|------|--------|------|--------|
| PUSH-001 | 发送失败时退还 credit | Critical | dispatcher.py | 2h |
| PUSH-002 | 所有推送消息强制添加 disclaimer | Critical | 全局 templates | 4h |
| PUSH-003 | iMessage relay 不可达时 fallback Email | High | dispatcher.py | 3h |
| PUSH-004 | 验证 notification recipient 匹配用户配置 | High | notifications.py | 2h |
---
## 四、合规问题 (P0 — 上线阻塞)
| ID | 标题 | 严重度 | 文件 | 工作量 |
|----|------|--------|------|--------|
| COMP-001 | 创建 Privacy Policy 页面 | Critical | web/app/privacy | 4h |
| COMP-002 | 创建 Terms of Service 页面 | Critical | web/app/terms | 4h |
| COMP-003 | 全局审核所有内容输出是否带 disclaimer | Critical | 全局 | 1d |
| COMP-004 | 用户数据删除功能 | High | API + Web | 2d |
---
## 五、产品体验 (P1 — MVP 必须)
| ID | 标题 | 工作量 | 状态 |
|----|------|--------|------|
| UX-001 | Sign Up 页面 | 1d | ✅ 已实现 |
| UX-002 | Login 页面 | 1d | ✅ 已实现 |
| UX-003 | Onboarding — Assets 页面 | 1d | ✅ 已实现 |
| UX-004 | Onboarding — Style 页面 | 1d | ✅ 已实现 |
| UX-005 | Onboarding — Channels 页面 | 1d | ✅ 已实现 |
| UX-006 | Dashboard 添加 Loading/Empty/Error 状态 | 2d | ⚠️ 部分 |
| UX-007 | Daily Push 设置页完善（时间选择器） | 1d | ❌ |
| UX-008 | 全局 Toast 通知组件 | 1d | ❌ |
| UX-009 | 修复 LLM 调用结果丢弃 bug | 1h | ❌ |
| UX-010 | Landing page 文案 A/B 优化 | 1d | ❌ |
---
## 五-B、PM 审查新增 (P0/P1 — Founder Review)
| ID | 标题 | 严重度 | 描述 | 工作量 |
|----|------|--------|------|--------|
| PM-001 | iMessage Brief 内容重构 | 🔴 P0 | 当前只发 "report is ready"，需实现完整 fused brief 模板（见 DAILY_IMESSAGE_BRIEF_SPEC.md） | 3d |
| PM-002 | Portfolio-Aware Daily Report | 🔴 P0 | 当前 daily report 是通用版，不融合用户 preferred_assets 和 portfolio 数据 | 2d |
| PM-003 | 用户推送时间可配 | 🟡 P1 | 当前固定 UTC 00:20，需基于用户时区和偏好 | 2d |
| PM-004 | CoinGecko 真实数据接入 | 🟡 P1 | 替换 mock market data，提升信任度 | 3d |
| PM-005 | iMessage 发送时间 | 🟡 P1 | 当前 00:20 UTC = 08:20 CST，需可配 | 1d |
| PM-006 | Privacy Policy 页面 | 🔴 P0 | 合规必须 | 4h |
| PM-007 | Terms of Service 页面 | 🔴 P0 | 合规必须 | 4h |
| PM-008 | 英文版 i18n 完整性检查 | 🟡 P1 | 确保所有页面的英文翻译不 fallback 到中文 key | 1d |
---
## 六、数据管道 (P1 — Beta 必须)
| ID | 标题 | 工作量 |
|----|------|--------|
| DATA-001 | CoinGecko API 接入（真实 market data） | 3d |
| DATA-002 | X API 接入（KOL sentiment） | 3d |
| DATA-003 | 数据去重逻辑 | 1d |
| DATA-004 | Stale data 检测和 freshness 标记 | 1d |
| DATA-005 | 数据源健康检查定时任务 | 2d |
---
## 七、Portfolio (P2 — Beta 阶段)
| ID | 标题 | 工作量 |
|----|------|--------|
| PORT-001 | 手动持仓输入 API + UI | 3d |
| PORT-002 | NAV 计算引擎 | 3d |
| PORT-003 | Portfolio page 接通真实数据 | 2d |
| PORT-004 | Portfolio-Aware Daily Brief 生成 | 2d |
| PORT-005 | NAV 历史记录和图表 | 2d |
---
## 八、NautilusTrader (P2 — v1.1)
| ID | 标题 | 工作量 |
|----|------|--------|
| NAUT-001 | NautilusTrader 环境搭建和集成 | 5d |
| NAUT-002 | 真实数据回测引擎 | 5d |
| NAUT-003 | 策略注册和选择 UI | 2d |
| NAUT-004 | Live trading 安全禁用机制 | 1d |
| NAUT-005 | Paper trading 模式 | 5d |
---
## 九、Enterprise (P3 — v1.2+)
| ID | 标题 | 工作量 |
|----|------|--------|
| ENT-001 | Bloomberg 数据适配器 | 10d |
| ENT-002 | Custom KOL 列表 | 3d |
| ENT-003 | Team Workspace | 10d |
| ENT-004 | Private Deployment 方案 | 15d |
| ENT-005 | PDF 报告导出 | 3d |
| ENT-006 | API Access for Enterprise | 5d |
---
## 十、技术债 (持续)
| ID | 标题 | 工作量 |
|----|------|--------|
| TECH-001 | 全局 `LLM_CALL_LOG` 改为 ring buffer | 2h |
| TECH-002 | `TTLCache` 添加定期清理 | 2h |
| TECH-003 | 分离 Celery broker 和 result backend | 2h |
| TECH-004 | 添加结构化日志（structlog/loguru） | 1d |
| TECH-005 | 添加 OpenTelemetry tracing | 2d |
| TECH-006 | 添加 Sentry error tracking | 1d |
| TECH-007 | 修复 `calculate_metrics` 使用样本方差 | 1h |
| TECH-008 | 移除 scheduler 重复的 scan_market_anomalies | 1h |
| TECH-009 | DB migration 框架（Alembic） | 2d |
| TECH-010 | API 文档自动生成（OpenAPI/Swagger） | 1d |
---
## 十一、backlog 统计
| 优先级 | 数量 | 预估总工作量 | 已完成 |
|--------|------|-------------|--------|
| P0 (上线阻塞) | 22 | ~12 天 | 0 |
| P1 (MVP 必须) | 14 | ~10 天 | 5 (UX-001~005) |
| P2 (Beta) | 9 | ~20 天 | 0 |
| P3 (v1.1+) | 10 | ~50 天 | 0 |
| 技术债 | 10 | ~9 天 | 0 |
**总计**: 65 个 issues，~101 天工作量（单人）。
---
## 十二、3 周冲刺计划（更新）
### Sprint 1（Week 1-2）：安全 + 计费 + 合规
Target: 解决所有 P0 安全/计费/合规问题
- SEC-001, SEC-002, SEC-003, SEC-004
- BILL-001, BILL-002, BILL-003
- PUSH-001, PUSH-002
- COMP-001, COMP-002, COMP-003
- PM-006, PM-007
### Sprint 2（Week 3-4）：核心产品体验
Target: iMessage Brief 重构 + Portfolio-aware Report
- PM-001 (iMessage Brief 内容重构 — 最高优先级)
- PM-002 (Portfolio-Aware Daily Report)
- PUSH-003, PUSH-004
- SEC-005, SEC-006
- UX-006, UX-007
### Sprint 3（Week 5-6）：数据 + 上线准备
Target: 首个真实数据源 + 推送配置
- PM-004 (CoinGecko 接入)
- PM-003, PM-005 (推送时间可配)
- COMP-004
- TECH-001 ~ TECH-004
- PM-008 (i18n 完整性)
- O11 (API docs)
