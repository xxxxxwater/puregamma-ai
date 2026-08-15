# LIVE Trading — 回滚方案

## 1. 代码回滚

LIVE 能力是**纯新增**:

- 迁移 `0026_live_trading_control_plane` 是 additive(外加对 `trading_mandates`
  的列重命名/新增);回滚顺序:
  ```bash
  cd /puregamma/app
  DATABASE_URL=... python -m alembic downgrade 0025_harness_research
  git checkout <上一个部署 commit>   # 不含 0026
  ```
  注意:`trading_mandates.allowed_symbols_json / approval_status` 会改回
  `asset_allowlist_json / approval_state`。PAPER/SHADOW 路径完全不受影响
  (LIVE 表独立)。
- 若只想停用 LIVE 而不回滚代码:见 `STATUS.md`「一键关闭」。

## 2. 数据保留

- `ledger_entries`、`risk_checks`、`fills`、`trading_reconciliations` 为
  INSERT-only,任何回滚都不删除历史;
- 回滚代码后旧表数据仍留在库中,可随时人工导出审计。

## 3. 恢复数据库

- 本地/服务器 `deploy/live-trading/offsite-encrypted-backup.sh` 每日加密
  备份;恢复:
  ```bash
  # 解密
  gpg --batch --passphrase-file /etc/puregamma/backup-passphrase \
      -d /var/backups/puregamma-encrypted/postgres-<TS>.dump.gpg \
      > /tmp/postgres.dump
  # 停 API/worker(避免写入)
  docker compose -f docker-compose.production.yml stop api worker scheduler
  docker compose -f docker-compose.production.yml exec -T postgres \
    pg_restore -U puregamma -d puregamma --clean --if-exists /tmp/postgres.dump
  docker compose -f docker-compose.production.yml start postgres api worker scheduler
  ```
- 恢复后必须(见 PRODUCTION_DEPLOYMENT.md §6):
  1. 交易所连接健康检查;
  2. 手动跑 `puregamma.daily_live_reconciliation`;
  3. 对账 OK 前所有 LIVE Mandate 保持 `paused=true`(默认行为:服务器重启后
     LIVE Mandate 不自动恢复)。

## 4. 恢复订单状态

1. 服务器重启后,LIVE Mandate 一律不自动恢复(部署文档强制);
2. 对状态 `unknown` 的订单:`puregamma.sync_live_order_statuses` 只**查询**
  交易所,不重发;查询结果写回 `live_orders.status`;
3. 若交易所已成交而本地未记账:对账任务产生差异 → 暂停 Mandate → 管理员在
  对账记录人工处理后,通过 admin 端点恢复;
4. 历史 Ledger **永不自动修改**;纠错通过新增
   `reconciliation_adjustment` 条目完成。

## 5. 部署标记回滚

`LIVE_TRADING_DEPLOYMENT_APPROVED=false` 后重启即可回到 LIVE_DISABLED;
`LIVE_TRADING_ENABLED=false` 是总闸。
