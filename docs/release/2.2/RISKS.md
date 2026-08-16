# 2.2 预部署 — 风险清单

| # | 风险 | 等级 | 缓解 | 状态 |
|---|---|---|---|---|
| 1 | 默认 tier=silver + admin 改 tier 同步 user.plan(silver→Pro)可能给非订阅用户 Pro 权益 | 中 | 只有 admin 显式操作才会改 tier;有活跃 Stripe 订阅的用户拒绝(409);entitlement 输出带 tier 供审计;测试覆盖 | 已缓解 |
| 2 | LIVE 意外全量开放 | 高 | 静态门 + 动态门双层;默认全 false;gateway=mock 拒绝真实下单;safety-status 恒 LIVE_DISABLED;NAUTILUS_ALLOW_WITHDRAWAL/TRANSFER 硬禁 | 已缓解 |
| 3 | providers.yaml Kimi 中国区/价格未 review 就上线 | 中 | 保持未提交;独立 review 后单独 PR | 待 review |
| 4 | /api/research/runs*、/api/memory/* 未实现,前端可能误展示 | 低 | capabilities 恒 false(端点未实现前);404 时前端显示不可用,5xx 不被吞成 unavailable(PR2 api.ts 已处理) | 已缓解 |
| 5 | Android 未在 JDK 17 环境跑 Gradle 测试 | 中 | IDE 静态诊断 0 error;单元测试已写;发布前必须在 CI/JDK17 环境执行 | 待执行 |
| 6 | 单机资源告警未验证真实阈值 | 低 | resource-alerts.sh + cron 文档已给;上线后首周人工核对阈值 | 待上线核对 |
| 7 | PostgreSQL 备份/恢复未在 staging 实测 | 中 | 脚本已核对服务器路径;上线前必须在 staging 做一次完整 restore 演练 | 待演练 |
| 8 | 历史数据库含 legacy `bronze` tier | 低 | `canonical_tier()` 读取归一化 silver;admin 拒绝 bronze 输入 | 已缓解 |
| 9 | PR1/PR2 仅 Web 改动、未覆盖移动端视觉 | 低 | 财务页面不含动画组件(代码级确认);移动端独立验收已过 | 已缓解 |
| 10 | 服务器重启后 LIVE Mandate 自动恢复 | 高 | 部署文档强制:重启后不自动恢复,人工连接检查+对账后恢复(运维流程) | 已缓解(流程) |

结论:高等级风险均已缓解;两个"待执行"项(Android JDK17 测试、staging 备份恢复演练)与一个"待 review"项(providers.yaml)必须在部署窗口内完成。
