# 2.2 预部署 — 测试命令与结果

## 后端(本机,Python 3.9 环境)

```bash
cd /Users/christse/Desktop/puregamma.ai/puregamma-ai
.venv/bin/python -m pytest tests/security -q
```

结果:**128 passed, 3 failed**。3 个失败为既有环境问题(本机 Python 3.9 LibreSSL
无 `hashlib.scrypt`,CI 用 3.12 通过),与本次变更无关:
`tests/security/test_internal_admin_login.py::test_internal_admin_password_hash_round_trip`
等 3 例。

关键新套件:
- `tests/security/test_admin_tier_update.py` — **10 passed**(admin silver/gold、
  Stripe active 409、plan 同步、past_due 基线、legacy bronze 拒绝、未知 tier 400)
- `tests/security/test_live_trading_foundation.py` — **16 passed**
- `tests/security/test_migration_chain.py` — head=0027,通过
- `tests/test_billing.py` + 上两者 — **40 passed**

## 前端 Web

```bash
cd apps/web && pnpm typecheck   # 通过(tsc --noEmit 无输出)
pnpm lint                       # 仅既有 warning,无 error
```

## iOS

```bash
cd apps/ios && xcodebuild test -project PureGamma.xcodeproj -scheme PureGamma \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro'
```

结果:**exit=0 全过**(含新增 `subscriptionToleratesMissingAndUnknownMembershipTier`)。

## Android

- 单元测试已写(`MobileModelsTest.userParsingToleratesMissingAndUnknownMembershipTier`
  等)。
- **本机无 JDK 17(按团队约束未安装),Gradle 未执行**。部署前必须在 CI/JDK17 环境:
  ```bash
  cd apps/android && ./gradlew :app:testDebugUnitTest
  ```

## 迁移演练

```bash
DATABASE_URL=sqlite:////tmp/xxx.db .venv/bin/python -m alembic upgrade head
DATABASE_URL=sqlite:////tmp/xxx.db .venv/bin/python -m alembic downgrade 0026_live_trading_control_plane
```
round-trip 通过;本地 dev 库已升级至 `0027_user_membership_tier`。
