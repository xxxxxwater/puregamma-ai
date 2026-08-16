# 2.2 预部署 — 回滚步骤

## 1. 代码回滚

`release/2.2-predeploy` 与 `main` 同时推进;回滚 = 部署上一个 commit:

```bash
# 服务器
cd /puregamma/app
git log --oneline -5            # 记录当前 HEAD
# 回滚代码(示例:回到 v0.2.1 对应的 0dbe9ce 之前状态需按实际部署 commit)
git checkout <上一个已验证 commit>
docker compose -f docker-compose.production.yml up -d --build api worker scheduler web
```

## 2. 数据库回滚(如需)

```bash
cd /puregamma/app
DATABASE_URL=... python -m alembic downgrade 0026_live_trading_control_plane
# 会员等级列(0027)随之删除;tier 逻辑在代码回滚后不引用该列
```

## 3. 恢复数据库与订单状态(详见 docs/live-trading/ROLLBACK.md)

1. 加密备份解密 → `pg_restore`(停 api/worker/scheduler 后执行);
2. 服务器重启后 LIVE Mandate **不自动恢复**:先连接健康检查 + 每日对账,OK 后人工恢复;
3. `unknown` 订单只查询交易所,不重发;Ledger 永不改写,差异走
   `reconciliation_adjustment`。

## 4. 一键关闭交易

- 应用层:`POST /admin/trading/kill-switch {"scope":"global","active":true,"reason":"..."}`
- 环境层:`LIVE_TRADING_ENABLED=false` + 重启 api/worker/scheduler(总闸)

## 5. 前端回滚

Next.js 静态构建无状态,回滚即部署旧 commit 的 web 镜像;移动端无需回滚
(仅读 capabilities,后端开关即降级)。

## 6. 回滚验证清单

- [ ] `GET /api/trading/safety-status` = LIVE_DISABLED
- [ ] `/api/mobile/capabilities` 各布尔与旧版一致
- [ ] Admin 等级页可用(Silver/Gold)
- [ ] 登录/OAuth/Stripe 不受影响
