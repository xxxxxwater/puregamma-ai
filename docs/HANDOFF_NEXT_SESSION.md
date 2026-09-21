# 下一会话交接提示词

> 直接复制下面 `---` 之间的内容作为新会话的第一条消息。

---

你是 PureGamma.ai 的主开发与部署工程师。本轮任务是**完成 Cordis 插件化重构（完整 cutover）**：把仍然由经典 FastAPI 路由 / Next 页面承担的四个功能逐个实现为 Cordis 插件，验证通过后删除经典实现，最后一次性部署。

## 一、现状：已完成，不要重做

**工作目录**：`/Users/christse/Desktop/puregamma.ai/puregamma-ai-harness-core-v2`

**分支**：`cutover/harness-full`（已推送 origin），HEAD = `a26434f merge(harness): bring the full refactor into main additively, keeping production intact`

该分支已经完成的事：

- refactor/harness-core-v2 的 20 个提交已全部合入（trading-mandates 插件、pg-tsy 健康契约、notification Remote 修复、CI 门禁、release-boundary 测试、`harness/INTEGRATION_RELEASE_GATE.md`）
- 迁移链 0030/0031/0032 保留，共 33 个迁移文件
- PM NAV、JEV 网关 + 顾问页、mobile_access、wallet_auth、chat_workspace、pagination、trading/live 4 个页面 —— 全部保留
- `next build` exit 0；32 个测试通过（PM 读取器 + JEV 决策 + 迁移链）
- 工作区干净

**合并无冲突**，因为 `git diff main refactor` 里那些"删除"是双向 diff 的假象：refactor 从更早的祖先分叉，main 后来新增的文件在它眼里是"缺失"。**不要再尝试"解决"这些删除。**

## 二、生产现状（未受本轮影响）

```
主机:      47.245.55.228  (root, key: ~/Desktop/puregamma.ai/vscode_DEEPSEEKV4_new.pem)
api:       puregamma-ai-api:harness-20260921b   healthy
web:       puregamma-ai-web:harness-20260921b   healthy
worker/scheduler: 0dbe7b48   pocket: mobile1-20260916   postgres/redis/caddy/nautilus: 未动
DB head:   0032_chat_workspace
数据基线:  users=21 | trading_accounts=1 | gateway_api_keys=10 | gateway_request_logs=8
```

**当前部署的 `harness-20260921b` 与本分支不同**：它少了 refactor 的 20 个提交，也少了 JEV 产品集成（意图路由 + 证据重排 + 模型选择器 Evaluation 类别）。本轮 cutover 会把它们一起带上。

**回滚资产（保留中）**：
```
/var/backups/puregamma/pre-harness-20260921T022516Z.dump          (数据库, 57MB)
/puregamma/app/.env.before-harness-20260921T022516Z
/puregamma/app/docker-compose.release-pin.yml.before-harness-20260921T022516Z
/puregamma/app/docker-compose.production.yml.before-3email-*
旧镜像: puregamma-ai-api:jev-20260919 / puregamma-ai-web:jev-20260919
```

## 三、必须遵守的硬约束

**1. 迁移链只增不改。** Alembic 迁移是已执行的历史。生产库 `alembic_version` = `0032_chat_workspace`。**永远不要删除或改写 0030/0031/0032。** 迁移在架构上**没有插件替代**——任何"用插件替代迁移"的想法都是错的。如果将来要加迁移，只做向后兼容的增量。

**2. 用户数据不可丢。** 部署前后必须核对 `users / trading_accounts / gateway_api_keys / gateway_request_logs` 四项计数。禁止删库重建、禁止清空迁移历史、禁止用备份覆盖发布后新增数据来回退。

**3. PM NAV 必须保留。** 三个邮箱的私有只读 NAV：
   - 白名单来自 `PM_ACCOUNT_ALLOWED_EMAILS`，**compose 的环境变量优先于 `config.py` 默认值**（此前正是这里出错导致第三个邮箱失去权限）
   - 只读挂载：`${PM_RISKBOT_EXPORT_DIR:-/srv/riskbot-export}:/var/lib/puregamma/riskbot:ro`
   - 服务端授权：`require_pm_account_viewer`，未配置白名单 = 拒绝所有人
   - 绝不并入用户总 NAV（`merged_into_portfolio_nav` 保持 false）
   - PureGamma 不持有交易所凭证，不具有下单能力

**4. 实盘边界不动。** `JEV_INTEGRATION.md` 明确：JEV 仅作建议，现有 PolicyEngine → Risk → journal → OMS → venue 路由保持权威。不得开启自动实盘。

**5. 不碰无关服务。** Freqtrade、PMBinanceJP、Riskbot、Nautilus、postgres、redis、caddy、pocket、worker、scheduler 一律不重建不重启。

## 四、本轮要完成的工作

为四个功能各建一个 Cordis 插件，**验证通过后再删经典实现**。按优先级：

### P1 — `harness/plugins/pm-nav`（最重要）

现状：经典实现分散在
```
apps/api/services/pm_riskbot_service.py          读取器（283 行）
apps/api/routers/portfolio.py                    GET /pm、GET /pm/history
apps/api/dependencies.py                         require_pm_account_viewer
apps/api/config.py                               pm_riskbot_export_dir / pm_account_allowed_emails / pm_account_label
apps/web/components/pm-account-panel.tsx         面板（554 行）
apps/web/components/portfolio-console.tsx        挂载点
apps/web/lib/api.ts                              PmAccountView / PmNavHistory + 两个取数函数
```

已核实：refactor 的 `portfolio` / `portfolio-legacy-api` / `tool-portfolio` 三个插件中 **riskbot / pm_account / allowed_emails 命中数均为 0** —— 没有现成实现，**必须新建**。

插件需包含：只读 bundle 读取、三邮箱服务端授权、`/portfolio/pm` 与 `/portfolio/pm/history` 两个只读端点、前端面板、配置项、fail-closed 测试（bundle 缺失/schema 不匹配/过期都要返回 `available:false` 而非伪造数据）。

### P2 — `harness/plugins/mobile-access`
经典实现：`apps/api/routers/mobile_access.py` + `apps/web/app/[locale]/mobile-access/page.tsx`。

### P3 — `harness/plugins/wallet-auth`
经典实现：`apps/api/routers/wallet_auth.py`（SIWE 验签）。

### P4 — `harness/plugins/chat-workspace`
经典实现：`apps/api/services/chat_workspace.py`。

每个插件完成后：跑测试 → 确认插件接管 → 才删经典实现。**不要先删后建。**

参考现有插件结构：`harness/plugins/trading-mandates`（最新的、结构最完整）、`harness/profile/cordis.patch.yml`（插件装配）。

## 五、已知陷阱（都踩过，别再踩）

1. **compose override 的 `image:` 指令会覆盖构建标签。** 带 `docker-compose.pmui-override.yml` 构建会把镜像打成它指定的名字。构建后务必核对实际标签并重新打可追溯标签。
2. **`validate_production_settings` 有独立的 provider 允许列表**（`config.py` 约 824 行），与适配器注册表分离。往里加 provider 必须同时更新两处，否则 API 启动即退出（已因此失败过一次）。
3. **`Settings` 类里的配置项必须真的在类内。** 曾把 `pm_*` 追加到文件末尾，落进 `validate_production_settings` 函数体成了死代码，导致 `AttributeError: 'Settings' object has no attribute 'pm_account_allowed_emails'`。
4. **行尾风格**：修改文件时保持该文件已有的 CRLF/LF。仓库部分文件是 CRLF，用 Python 读写要用 `open(..., newline="")`，否则会产生整文件假 diff（曾把 3 行改动变成 555 行）。
5. **`/puregamma/app` 不是 api/web 源码**，是旧树（缺 0032 迁移）+ compose/env/Caddyfile 所在地。**不要从它重建 api**，会让 API 启动失败。
6. **`/puregamma/app/.git` 是指向 Mac 路径的失效 worktree 指针**，在该目录执行 git 无意义。
7. **SSH 会触发 sshd 限流**（`kex_exchange_identification: Connection closed`）。等待 60–90 秒重试即可，不要连续猛试。
8. **本机 VPN 把 `*.puregamma.ai` 劫持成 fake-IP**（198.18.0.x），本地无法直接访问生产站点。验证页面要在服务器上用容器内方式，或让用户从浏览器确认。

## 六、部署流程（插件全部完成并验证后才执行）

```bash
# 1. 备份
docker exec puregamma-ai-postgres-1 pg_dump -U puregamma -d puregamma \
  --format=custom --no-owner --no-privileges > /var/backups/puregamma/pre-cutover-<STAMP>.dump
cp -p /puregamma/app/.env /puregamma/app/.env.before-cutover-<STAMP>
cp -p /puregamma/app/docker-compose.release-pin.yml /puregamma/app/docker-compose.release-pin.yml.before-cutover-<STAMP>

# 2. 记录基线
docker exec puregamma-ai-api-1 alembic current          # 必须为 0032_chat_workspace
docker exec puregamma-ai-postgres-1 psql -U puregamma -d puregamma -tAc \
  "select (select count(*) from users),(select count(*) from trading_accounts),(select count(*) from gateway_api_keys),(select count(*) from gateway_request_logs)"

# 3. 从 cutover 分支导出源码树 → 上传 → 解包到新目录（不覆盖历史 build 目录）
git archive --format=tar.gz -o /tmp/cutover.tgz <branch>
rsync -az --partial -e "ssh -i <KEY>" /tmp/cutover.tgz root@47.245.55.228:/tmp/
# 服务器上: mkdir /puregamma/build-cutover-<DATE> && tar xzf

# 4. 构建（务必核对 override 的 image 指令）
cd /puregamma/build-cutover-<DATE>
docker compose --env-file /puregamma/app/.env -f docker-compose.production.yml build --no-cache api web
docker tag ... puregamma-ai-api:cutover-<DATE> / puregamma-ai-web:cutover-<DATE>

# 5. 更新 release-pin（只改 api 与 web 两行）
sed -i 's|image: puregamma-ai-api:.*|image: puregamma-ai-api:cutover-<DATE>|;
        s|image: puregamma-ai-web:.*|image: puregamma-ai-web:cutover-<DATE>|' \
    /puregamma/app/docker-compose.release-pin.yml

# 6. 定点更新（不带 pmui-override）
cd /puregamma/app
docker compose --env-file /puregamma/app/.env \
  -f docker-compose.production.yml -f docker-compose.release-pin.yml \
  up -d --no-build --no-deps api web

# 7. 验收（任一失败立即回滚）
#    - alembic head 仍为 0032_chat_workspace
#    - 四项数据计数与基线一致
#    - allowed_emails() == 3，PM NAV available=True
#    - /v1/systemone 真实调用 + 计费对账（$0.042 官方 / $0.0546 零售，输出免费）
#    - /api/frontend/plugins 返回 manifest
#    - deepseek/kimi/glm 旧模型无回归
#    - 页面：/zh /en /zh/jev-trader /portfolio /mobile-access /trading/live/*

# 回滚
cp -p /puregamma/app/docker-compose.release-pin.yml.before-cutover-<STAMP> /puregamma/app/docker-compose.release-pin.yml
cd /puregamma/app && docker compose --env-file .env \
  -f docker-compose.production.yml -f docker-compose.release-pin.yml \
  up -d --no-build --no-deps api web
```

## 七、门禁与交付要求

`harness/INTEGRATION_RELEASE_GATE.md` 区分三道门禁：**合并**、**生产 UI**、**实盘执行**。本轮只申请过前两道。

- 不要只凭"容器 healthy"或"首页 200"宣布成功
- 不要用 mock、静态页或伪造数据冒充已上线功能
- 页面验收必须真实打开确认（本机 VPN 劫持域名，需在服务器侧或用容器内探测）
- 若某插件无法完成，**保留经典实现**，如实报告阻塞点，不得先删后补
- 不要推送未审阅的变更到 main；cutover 完成后交用户确认再合

## 八、当前未完成项（如实记录）

- `pm-nav` / `mobile-access` / `wallet-auth` / `chat-workspace` 四个 Cordis 插件**均未创建**
- 经典实现**全部保留**，尚未删除
- JEV 产品集成（`f6cbff9`：意图路由 + 证据重排 + Evaluation 类别）已合并但**未部署**，默认关闭（`JEV_INTENT_ROUTING_ENABLED=false`、`JEV_RERANK_ENABLED=false`）
- refactor 的 20 个提交已合并但**未部署**

---

## 附：本轮已完成的提交

```
a26434f  merge(harness): 完整 refactor 加法合入，生产功能全保留
f6cbff9  feat(jev): JEV 意图路由 + 证据重排
e6f76cd  fix(config): PM 设置移入 Settings 类
799aa83  fix(web): 导出 JEV advisory 状态类型
3d64a34  feat(jev): 顾问状态页
78daf72  chore(vendor): 子模块 → f5a6382 (PR #9)
207461c  fix(pm-nav): 补回第三个授权邮箱
255f0eb  fix(pm-nav): 恢复三邮箱私有 PM NAV
f76a841  feat(jev): 计费网关与 advisory 并存
```
