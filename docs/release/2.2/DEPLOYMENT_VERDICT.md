# 2.2 预部署 — 发布结论

## 逐项对照发布条件

| 条件 | 状态 |
|---|---|
| `git status --short` 干净 | ⚠️ 部分:release 相关全部已提交;遗留 = providers.yaml(M,待独立 review)、site-plugin(M)、未跟踪待归属文件(见 CHANGELIST)。**发布分支本身干净**(release/2.2-predeploy 不含这些文件) |
| PR1/PR2 已合并 | ✅ main 已含两个 merge commit |
| 会员等级 bug 已修复并有测试 | ✅ 10 后端用例 + iOS/Android 容错用例 |
| LIVE 默认保持 disabled | ✅ safety-status=LIVE_DISABLED;所有门默认 false |
| NAV 不造假 | ✅ nav=null → 前端 `--`;后端 stale 不估值 |
| Mobile/Web capabilities 行为一致 | ✅ /api/mobile/capabilities 真实门控;web CapabilityGate;5xx 不被吞 |
| 数据库迁移演练通过 | ✅ 0027 round-trip + 本地库升级 |
| 备份和恢复验证通过 | ⚠️ 脚本路径已核对;PostgreSQL restore 完整演练必须在 staging 执行(本机无 docker) |
| 服务器资源告警启用 | ⚠️ 脚本与 cron 文档就绪;启用与阈值核对在服务器执行 |

## 结论

**条件允许进入部署**(预部署),前提是部署窗口内完成以下三项收尾:

1. **staging 执行一次 PostgreSQL 加密备份 + restore 演练**(本机无 docker,无法本地完成);
2. **Android 在 JDK 17/CI 环境跑 `./gradlew :app:testDebugUnitTest`**;
3. **`config/gateway/providers.yaml`(Kimi 中国区 + 价格)独立 review**,review 通过前该文件不进入任何部署(当前未提交)。

生产部署顺序见 `docs/live-trading/PRODUCTION_DEPLOYMENT.md`:
部署代码 + `alembic upgrade head` → 服务全启 → broker connection/test →
逐个用户 LIVE 审批 → Mandate 审批 → 部署标记 → 最后 `LIVE_TRADING_ENABLED`。

**签字:** 待团队确认(上述 3 项完成即可部署)。
