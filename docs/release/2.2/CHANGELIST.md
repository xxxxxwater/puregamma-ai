# 2.2 预部署 — 变更清单

## Git 收口(2026-08-16)

| Commit | 内容 |
|---|---|
| `f01e6ca` | Merge PR1 `feature/agent-research-visual-system`(基于 main 的 e782a88,1 commit,20 文件,web-only) |
| `81cb96b` | Merge PR2 `feature/financial-surfaces-stabilization`(精确基于 PR1 HEAD,1 commit,11 文件,web-only) |
| `c425a3d` | 会员等级 canonical Silver/Gold(后端/Admin/Web/iOS/Android 一致) |
| `03b71d8` | `/api/mobile/capabilities` 契约端点 |
| `f720262` | 发布卫生:backup 路径核对、.gitignore、mobile 发布文档 |
| `43cc705` | iOS/Android 未知等级容错测试 |

- 合并方式:`--no-ff`,main 直接合入;PR1/PR2 与 main 均无冲突(合并前已 dry-run)。
- `release/2.2-predeploy` = 合并后 main HEAD(`81cb96b` + 后续 commit)。
- 恢复:`mobile-release.yml`、`apps/ios/releases/README.md`(此前工作区删除,已 `git checkout` 恢复)、`.deployed-commit`(已 `git restore`)。
- `scripts/production-backup.sh`:`/puregamma/data/nautilus_state` 已 SSH 核对服务器(目录存在;服务器 compose 第 58 行同路径 bind mount)。
- **未提交(独立 review/待归属)**:
  - `config/gateway/providers.yaml`(Kimi 中国区 api.moonshot.cn + 6.6 CNY/USD 换算价格)—— 独立 review 项;
  - `apps/site/build/sites-vite-plugin.ts`、`apps/web/components/admin-gate.tsx`、`apps/web/components/how-it-connects.tsx`、`packages/backtest/{strategy_compiler,tools}.py`、`packages/trading/schemas/strategy_specs.py`、`scripts/ios-build-release.sh` —— 待归属;
  - 7 个 SVG、`releases/`、`docker-compose.production.yml.bak-migrate` —— 不入库(.gitignore 已覆盖后两类)。

## 会员等级(白银/黄金)

- canonical 集合 `{silver, gold}`(`packages/billing/plans.py`:TIERS/PLAN_TO_TIER/canonical_tier/plan_for_tier);`bronze` 为 legacy,读取归一化为 silver,admin 拒绝。
- Admin 允许列表 `{silver, gold}`;活跃 Stripe 订阅(active/trialing、非 Free/Invite Preview)→ 409 拒绝(订阅只能走 Stripe);无订阅用户 tier 同步 `user.plan`(silver→Pro,gold→Max),entitlement 随之生效。
- entitlement 输出新增 `membership_tier`;`plan/subscribed_plan/effective_plan` 语义不变;past_due → Free 基线 + restricted_reason(不变)。
- Stripe 同步时 `membership_tier = tier_for_plan(plan)` 保持徽章一致。
- Web:Admin 按钮 silver/gold、PlanBadge tier→白银/黄金;iOS/Android:订阅/用户模型新增可选 `membership_tier`,显示等级标签(本地化),未知值回退 plan 文案,不崩溃。

## LIVE / NAV(生产策略,全部默认关闭)

- `LIVE_TRADING_ENABLED=false`、`LIVE_TRADING_DEPLOYMENT_APPROVED=false`、`LIVE_TRADING_GATEWAY=mock`、`NAUTILUS_LIVE_TRADING_ENABLED=false`、`NAUTILUS_ALLOW_LIVE_ORDER=false`(compose/env 默认)。
- `/api/trading/safety-status` 返回 `LIVE_DISABLED`;`/api/portfolio/nav` 上线,NAV=null 时前端显示 `--` 不伪造。
- 灰度(未来):1 broker、1–3 白名单用户、spot-only、小额 mandate、禁提现/转账 API key、global kill switch 与每日对账已演练。
- 订单超时 → UNKNOWN,只查询不重试(既有 control plane 语义)。
- 移动端无 LIVE 下单入口(客户端硬约束)。
- Harness/Agent/Research 只产出研究/策略草案,不绕过 Control Plane。

## 后端 API 契约

- ✅ `/api/mobile/capabilities`(新)、`/api/trading/mandates*`、`/api/trading/safety-status`、`/api/portfolio/nav`。
- ❌ 未实现(诚实 404,前端显示"功能暂不可用"):`/api/research/runs*`、`/api/memory/*` — 见 UNIMPLEMENTED_ENDPOINTS.md。

## 前端 Web(PR1/PR2 验收)

- PR1:OceanShell/OceanBackground;`prefers-reduced-motion`→static;手机(≤767px)静态渐变;tab hidden 暂停 rAF;SSE 断线静默轮询(不误标失败);无思维链展示;无 LIVE 下单入口。
- PR2:Portfolio/NAV/Trading Safety 静态清晰;StaleDataBanner 显著;LIVE_DISABLED 明确;NAV null → `--`;Memory 全部经 CapabilityGate;财务页面无水波/发光/弱化动画。
- `pnpm typecheck` 通过;`pnpm lint` 仅既有 warning。

## iOS/Android 验收

- iOS:`xcodebuild test`(iPhone 17 Pro 模拟器)通过 exit=0;capabilities 门控、deep link 不崩、Memory 确认、Trading Safety 无 LIVE 操作、cache key 含 user/environment(上一轮已核)。
- Android:capabilities+repository 双重门控、WebView allowlist(BuildConfig)、深链仅受信路由、id 校验;新增等级容错测试;Gradle 需 JDK 17 环境执行(本机无 JDK,IDE 诊断 0 error)。

## 部署演练(本地 sqlite 模拟,详见 SMOKE_RECORD.md)

Alembic→0027、API 启动、capabilities/NAV/safety-status/mandates/billing/admin tier/kill-switch 均通过;scheduler 单实例锁已加。
