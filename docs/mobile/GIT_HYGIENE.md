# Git 工作区拆分与发布卫生（2026-08-15）

> 评审结论：当前 `main` 工作区包含与本次移动端升级无关的删除/修改，不得与移动端变更混交。

## 当前工作区分类

已提交到 HEAD（40bc306）的移动端升级代码不在下表；下表为**未提交**变更：

### A. 本次移动端升级相关（应单独提交，已包含评审修复）

| 文件 | 说明 |
|---|---|
| `apps/android/app/src/main/AndroidManifest.xml` | 新增 `puregamma://research/runs/*` 深链 |
| `apps/android/app/src/main/java/ai/puregamma/android/ui/PureGammaApp.kt` | Web 覆盖层/能力行/图标导入 |
| `apps/android/app/src/main/java/ai/puregamma/android/ui/WebProductScreen.kt` | 域名白名单 BuildConfig 派生、Scheme 拦截、主框架重定向复验、阻断下载 |
| `docs/mobile/*.md`（新增 4 份 + 本文件） | 契约/安全清单/发布说明/回滚/变更清单 |

### B. 与移动端无关（不得混入本次交付）

| 文件/目录 | 分类 | 建议 |
|---|---|---|
| `.github/workflows/mobile-release.yml`（D，77 行） | CI | **必须先解释删除原因**。历史：dffc7d4 引入、bdcc0f8/ca85ec5 完善（发布 APK/IPA）。删除将失去移动端发布能力 |
| `apps/ios/releases/README.md`（D，51 行） | iOS 发布文档 | 同样需解释；建议恢复 |
| `apps/site/build/sites-vite-plugin.ts`（M，90 行） | Web 站点 | 另开分支/单独提交 |
| `config/gateway/providers.yaml`（M，14 行） | 网关配置 | 另开分支/单独提交；**不要在本机改生产配置** |
| `scripts/production-backup.sh`（M，2 行） | 运维脚本 | 单独提交 |
| `.deployed-commit`（M，2 行） | 部署标记 | 通常不入库，建议 `git restore` |
| `BTC.svg` 等 7 个 SVG | Logo 资源 | 单独提交 |
| `apps/web/components/admin-gate.tsx`、`how-it-connects.tsx` | Web 组件 | 单独提交 |
| `packages/backtest/strategy_compiler.py`、`tools.py`、`packages/trading/schemas/strategy_specs.py` | 后端策略 | 单独提交 |
| `releases/`、`scripts/ios-build-release.sh`、`docker-compose.production.yml.bak-migrate` | 构建产物/备份 | 不入库；加入 `.gitignore` 或删除 |

## 建议拆分顺序（主开发执行）

```bash
# 1. 移动端提交（A 组 + 已暂存的移动端改动）
git add apps/android/app/src/main/AndroidManifest.xml \
        apps/android/app/src/main/java/ai/puregamma/android/ui/PureGammaApp.kt \
        apps/android/app/src/main/java/ai/puregamma/android/ui/WebProductScreen.kt \
        apps/android/app/src/main/java/ai/puregamma/android/data/repository/MobileRepositories.kt \
        apps/android/app/src/main/java/ai/puregamma/android/AppViewModel.kt \
        docs/mobile
git commit -m "feat(mobile): capabilities gate, ID validation, WebView hardening"

# 2. 文档单独提交
git add docs/mobile
git commit -m "docs(mobile): contract, security checklist, rollback, release notes"

# 3. 无关变更：另开分支或单独说明（勿混入移动端 PR）
git checkout -b chore/site-and-ops
git add apps/site config/gateway scripts packages apps/web releases 等
git commit -m "chore: site/gateway/strategy changes (review separately)"

# 4. 恢复误删（若删除非有意）
git restore .github/workflows/mobile-release.yml apps/ios/releases/README.md
git restore .deployed-commit
```

## 必须确认的两个删除

1. `.github/workflows/mobile-release.yml` —— 删除后 Android APK / iOS IPA 的 GitHub Releases 发布不再执行。若无替代 CI，必须恢复。
2. `apps/ios/releases/README.md` —— iOS 发布流程说明，删除后新成员无发布指引。若无替代文档，必须恢复。

## 本机环境约束（记录在案）

- 本机 macOS 无 JDK 17（按用户要求不安装），**Android 未在本机完成 Gradle 构建/测试**，必须在 CI 或有 JDK 17 的环境验证。
- 本机不得修改生产 `.env`、服务器配置或数据库。
- iOS 已在本机 `xcodebuild build` + `test` 通过（iPhone 17 Pro 模拟器，含既有与新增测试）。
