# private-PM 运维手册

核对基线：分支 `server/pm-live-20260916`。本文涉及的 PM 文件在 `83b753b` 上逐行核对（其后的 `0425831` 未改动任何 PM 文件）。
本文只包含**只读**的检查命令与已验证的部署保留流程；不含任何下单/撤销/资产操作（该链路在代码里不存在任何写入路径，见 `ARCHITECTURE.md` 第 3 节）。

> **English summary** — Operations guide for the read-only private-PM feed: configuration, read-only health checks, the deploy-preservation workflow, and a troubleshooting order. Every command here is read-only.

---

## 1. 配置项清单

三处定义在 `apps/api/config.py` 第 125–140 行；容器侧接线在 `docker-compose.production.yml` 第 162–165、174–177 行；示例值在 `deploy/production.env.example`（只有 `PM_ACCOUNT_ALLOWED_EMAILS` 一项）。

| 配置项 | 代码默认值 | 为空/缺失时的行为 | 影响面 |
| --- | --- | --- | --- |
| `PM_RISKBOT_EXPORT_DIR` | `"/var/lib/puregamma/riskbot"` | **功能整体关闭**：`get_reader()` 用 `Path("")` → `Path("/nonexistent")`（`pm_riskbot_service.py` 第 272–275 行），端点仍存在但恒返回 `available: false`、`reason: "riskbot export bundle not found"` | 服务端读取目录 |
| `PM_ACCOUNT_ALLOWED_EMAILS` | `"daigen999@gmail.com,xxxxxwater@gmail.com,perp24308@gmail.com"` | **拒绝所有人（fail closed）**：`allowed_emails()` 返回空元组，`is_allowed_email()` 对任何邮箱都是 `False` → 所有 PM 路由 403（`PM_ACCOUNT_NOT_AUTHORIZED`） | 服务端授权 |
| `PM_ACCOUNT_LABEL` | `"Binance Portfolio Margin"` | 无失败行为：只是一个展示标签，随 `GET /portfolio/pm` 的 `label` 字段下发 | 展示文案 |

### 1.1 `PM_ACCOUNT_ALLOWED_EMAILS` 的三条行为细节

1. **空字符串 = 拒绝所有人**，包括账户所有者自己。`config.py` 注释原文：`An empty value denies everyone: misconfiguration fails closed, and hiding the UI is never treated as authorization.` 这是设计选择，不是故障。
2. **解析规则**：`,` 与 `;` 都是分隔符；每项 `strip()` + 小写化（`normalize_email`）；保序去重。因此 `A@X.com, a@x.com` 等价于一个条目。
3. **判定对象是登录会话对应的 `user.email`**，与用户是否已注册无关——白名单可以在第二个账号登录之前就配好（`dependencies.py` 文档字符串：`The check is by verified account email, so it keeps working before the second account has even signed up`）。

### 1.2 目录接线

```yaml
# docker-compose.production.yml
environment:
  PM_RISKBOT_EXPORT_DIR: /var/lib/puregamma/riskbot          # 容器内固定路径
  PM_ACCOUNT_ALLOWED_EMAILS: ${PM_ACCOUNT_ALLOWED_EMAILS:-daigen999@gmail.com,xxxxxwater@gmail.com,perp24308@gmail.com}
  PM_ACCOUNT_LABEL: ${PM_ACCOUNT_LABEL:-Binance Portfolio Margin}
volumes:
  - ${PM_RISKBOT_EXPORT_DIR:-/srv/riskbot-export}:/var/lib/puregamma/riskbot:ro
```

要点：**容器内路径是固定的 `/var/lib/puregamma/riskbot`**；宿主目录由 `PM_RISKBOT_EXPORT_DIR` 决定（缺省 `/srv/riskbot-export`）。`:ro` 是刻意的——挂载点注释：`PureGamma never holds this account's exchange credentials and must never be able to write to the collector's output.`

> **English summary** — Three settings: `PM_RISKBOT_EXPORT_DIR` (default `/var/lib/puregamma/riskbot`; empty disables the feature into a permanent "bundle not found"), `PM_ACCOUNT_ALLOWED_EMAILS` (default lists three addresses; **empty denies everyone, fail closed**) and `PM_ACCOUNT_LABEL` (display only). The container path is fixed; the host path comes from `${PM_RISKBOT_EXPORT_DIR:-/srv/riskbot-export}` and is mounted `:ro`.

---

## 2. 确认 PM 是否正常（只读命令）

以下命令都在生产主机上以 `docker compose -f docker-compose.production.yml …` 运行，全部只读。

**a) 生效的白名单**（应看到已规范化的小写邮箱元组；空元组 `()` 就是"拒绝所有人"）：

```bash
docker compose -f docker-compose.production.yml exec api \
  python -c "from apps.api.services.pm_riskbot_service import allowed_emails; print(allowed_emails())"
```

**b) 容器内看到的 bundle：schema、生成时间、文件年龄（秒）**：

```bash
docker compose -f docker-compose.production.yml exec api python -c "
import json, os, time
for name in ('latest.json', 'series.json'):
    p = '/var/lib/puregamma/riskbot/' + name
    try:
        with open(p) as fh:
            d = json.load(fh)
        print(name, d.get('schema'), d.get('generated_at'), 'age_s=', round(time.time() - os.stat(p).st_mtime))
    except Exception as exc:
        print(name, 'ERROR', exc)
"
```

判读：`age_s` 远小于 180 且 `schema` 与读取器常量一致即为正常；`age_s > 180` 会让页面显示 **STALE**；`FileNotFoundError` 会让页面显示"不可用（riskbot export bundle not found）"。

**c) 挂载确实是只读的**：

```bash
docker compose -f docker-compose.production.yml exec api sh -c "grep riskbot /proc/mounts"
```

应看到以 `ro` 结尾的挂载项。若没有这一行，说明 volume 接线丢了。

**d) 路由存在**（区分"没数据"和"这个构建里根本没有 PM 代码"）：

```bash
docker compose -f docker-compose.production.yml exec api python -c "
import urllib.request, urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:8000/portfolio/pm')
except urllib.error.HTTPError as e:
    print('HTTP', e.code)
"
```

- `401` = 路由存在且要求认证（**期望结果**，因为这条命令没有带会话）；
- `404` = 这个构建里没有 PM 路由 → PM 代码没有进这棵树，见第 3 节；
- `200` = 仅当容器外的网关绕过鉴权时才会出现，属于异常，需要立即排查。

**e) 工具与清单在位**：

```bash
bash /puregamma/deploy/pm-preserve.sh paths | wc -l          # 期望 16
bash /puregamma/deploy/pm-preserve.sh verify --tree /puregamma/pm-overlay
```

> **English summary** — Five read-only checks: the effective allowlist tuple, the bundle's schema/generated_at/mtime age inside the container, the `ro` mount in `/proc/mounts`, a 401-vs-404 probe of `/portfolio/pm` (401 is the expected, healthy answer), and `pm-preserve paths | wc -l` (16) plus a `verify` on the canonical overlay.

---

## 3. 部署保留机制（重要）

### 3.1 为什么需要它

PM 代码**刻意不进 main**：它是 `server/pm-live-20260916` 相对 `main` 的差异。清单 `deploy/pm-paths.txt` 由 `git diff --name-only main <pm-branch>` 生成（见 commit `b93947b` 的提交信息：`deploy/pm-paths.txt is generated from git diff --name-only main <pm-branch>, so the manifest cannot drift from the branch it describes.`），共 **16 个路径**。

后果被实测过（本次核对用 `git cat-file -e main:<path>` 逐个验证，结论与提交信息一致）：

- **干净 main 检出只有 13/16 个 PM 文件**；
- 缺的正是 **3 个 PM 独有文件**：
  - `apps/api/services/pm_riskbot_service.py`
  - `apps/web/components/pm-account-panel.tsx`
  - `tests/test_mobile_access_handoff.py`

因此**从 main 起手的构建目录天然没有 PM**，而**直接 rsync 覆盖线上树**会把已有的 PM 文件改回去。PM 因此按"像数据库一样对待"的方式管理：部署前备份、可事后恢复，不依赖部署源树而存在（`pm-preserve.sh` 头部注释原文：`So PM is treated like the database: it is backed up before a deploy and can be restored afterwards, and it never depends on the deploy source tree for its continued existence.`）。

> 备注：相对 main 的差异总共是 **18 个文件** = 清单里的 16 个 + 工具自身两个（`deploy/pm-paths.txt`、`deploy/pm-preserve.sh`）。工具不在自己的清单里。

### 3.2 服务器上的落地位置

| 用途 | 路径 |
| --- | --- |
| 工具 | `/puregamma/deploy/pm-preserve.sh`（连同 `pm-paths.txt`，两者必须同目录） |
| canonical 副本（16 个 PM 文件的权威来源） | `/puregamma/pm-overlay/` |
| 备份归档 | `/puregamma/pm-backups/` |

代码层面唯一硬编码的默认目录是备份目录：`DEFAULT_OUT="${PM_BACKUP_DIR:-/puregamma/pm-backups}"`；`--tree` / `--from` / `--to` 一律显式传入。清单默认位置是 `<脚本所属仓库根>/deploy/pm-paths.txt`，可用 `PM_MANIFEST` 覆盖。

**调用方式有讲究**：`ROOT_DIR` 由 `BASH_SOURCE[0]` 的目录名向上取一级而来，所以要用 `bash deploy/pm-preserve.sh …`（在仓库根执行）或绝对路径 `/puregamma/deploy/pm-preserve.sh …`。若把脚本复制到别处再以裸文件名调用，`ROOT_DIR` 会解析成"当前目录的父目录"，从而找不到清单并 `exit 1`（本次已实测：`pm-preserve: manifest not found: …`）。

### 3.3 四个子命令

退出码约定（脚本头部注释）：**0 成功，1 用法/IO 错误，2 某个 PM 路径缺失或不可读**。

```bash
bash deploy/pm-preserve.sh paths                                  # 打印清单里的 16 个路径
bash deploy/pm-preserve.sh verify  --tree DIR                     # 只检查，不写任何文件
bash deploy/pm-preserve.sh backup  --tree DIR --out DIR           # 时间戳 tar，像 pg_dump
bash deploy/pm-preserve.sh restore <archive.tar.gz> --tree DIR    # 修复丢了文件的目录
bash deploy/pm-preserve.sh sync    --from DIR --to DIR            # 把 PM 叠加到构建目录
```

| 子命令 | 行为（代码位置 `deploy/pm-preserve.sh`） |
| --- | --- |
| `paths` | 逐行打印清单（跳过空行与 `#` 注释） |
| `verify --tree DIR` | 缺文件时**逐条**在 stderr 打印 `pm-preserve: MISSING <路径>`，并以 **2** 退出；全部在位时打印 `pm-preserve: OK — 16 PM paths present under DIR`，退出 0 |
| `backup --tree DIR --out DIR` | 先 `require_tree`（树不完整就 exit 2，**不会**悄悄打一个小一点的包）；`install -d -m 0700` 建立输出目录；归档名 `pm-<UTC 时间戳>-<PID>.tar.gz`，`chmod 600`。PID 后缀是为了避免"同一秒内的两次备份互相覆盖"（这正是 commit `83b753b` 修的缺陷）。`tar` 直接吃清单，因此路径消失会报错而不是静默缩小归档 |
| `restore <archive> --tree DIR` | `tar xzf` 解到树里，然后**再次** `require_tree` 验证（仍不完整则 exit 2）。这就是"修复丢了文件的目录"的路径 |
| `sync --from DIR --to DIR` | 逐路径 `cp -p`（保留时间戳与权限）；源缺文件立即 `SOURCE MISSING` + exit 2；`--from` 与 `--to` 是同一目录时为 no-op；结束时对目标再跑一次 `require_tree`——**部署脚本必须证明 PM 真的落地了**（注释：`A deploy target that lacks the PM files is the failure this script exists to prevent, so prove it landed.`） |

可移植性：脚本刻意不用 `install -D`（BSD install 没有该选项），以同时支持准备发布用的 macOS 与线上 Linux（脚本内注释）。

### 3.4 已验证的端到端结果

commit `b93947b` 的提交信息记录了对着干净 main worktree 的实测：

| 场景 | 结果 |
| --- | --- |
| 干净 main 树上 `verify` | exit 2，点名缺的 3 个 PM 独有文件 |
| `backup` | exit 0，16 个路径 |
| `sync` → 目标树 | exit 0，16/16 在位，**0 字节差异** |
| 清空后 `restore` | exit 0，16/16 在位，**0 字节差异** |

本次核对独立复现了两条：在当前分支树上 `verify` 得 `pm-preserve: OK — 16 PM paths present under .`（exit 0）；对一棵缺文件的临时树 `verify` 逐条报出 16 个 `MISSING` 并 exit 2。

### 3.5 发布流程中的位置

1. **部署前**：`backup --tree <当前线上/构建树> --out /puregamma/pm-backups`。
2. 从 main 起手构建（此时该树只有 13/16 个 PM 文件）。
3. **`sync --from /puregamma/pm-overlay --to <构建树>`** 把 PM 叠加进去；若 `sync` 返回 2，先修 overlay，不要继续。
4. 对此前的线上树与新的构建树各跑一次 `verify`。
5. 部署后按第 2 节的 b/d 两项确认 bundle 与路由。
6. 若某棵树丢了文件：`restore <最新归档> --tree <该树>`，再 `verify`。

> **English summary** — PM lives only on `server/pm-live-20260916`; `deploy/pm-paths.txt` (generated from `git diff --name-only main <pm-branch>`) lists 16 paths, and a clean main checkout contains just 13/16 — missing exactly `pm_riskbot_service.py`, `pm-account-panel.tsx` and `test_mobile_access_handoff.py`. `deploy/pm-preserve.sh` therefore treats PM like the database: `verify` (exit 2, naming each missing path), `backup` (timestamped tar, PID-suffixed), `restore`, `sync` (which proves the target afterwards). On the server: tool in `/puregamma/deploy/`, canonical copy in `/puregamma/pm-overlay/`, archives in `/puregamma/pm-backups/`.

---

## 4. 排障：页面显示不可用/过期时的检查顺序

按"先排除授权、再排除文件、最后才是采集器"的顺序走，**每一步只回答一个问题**。

1. **这是不是授权问题？**
   接口 403 且前端的 `reason` 为 `"forbidden"` → 面板整体不渲染，这就是未授权。核对：登录邮箱是否在 `PM_ACCOUNT_ALLOWED_EMAILS`（第 2 节 a 命令）里；配置是否被误设成空串（空串 = 拒绝所有人，包括 owner）。服务端会记 `pm_account_access_denied`（含 `user`、`email`、`allowlist_size`）便于确认。

2. **页面上那句 `reason` 是什么？**
   不可用卡片会原样带出服务端原因，直接对应失败模式：`riskbot export bundle not found` / `unreadable: …` / `malformed bundle: …` / `bundle is not an object` / `unsupported bundle schema '…'`。看到哪一句就跳到对应那一行处理，不必猜。

3. **文件在不在、多旧？**
   跑第 2 节 b 命令。三种典型结论：
   - 文件不在 → 查 riskbot 是否在写、宿主目录是否挂错（第 2 节 c）；
   - `age_s > 180` → 采集停了或对账卡住，页面显示 STALE；
   - `schema` 与 `puregamma.pm_account.v1` / `puregamma.pm_nav_series.v1` 不一致 → 生产端改了契约却没升/没同步版本号，**读取器会拒收，这是预期行为**（见 `DATA_CONTRACT.md` 第 5 节）。

4. **页面在 404 或什么都没有？**
   先跑第 2 节 d。`404` 而不是 `401` 意味着这棵构建树里没有 PM 路由——直接进第 3 节：`pm-preserve.sh verify --tree <该树>` 会点名缺哪些文件，然后用 `sync` 或 `restore` 修。

5. **数字有了但仍显示 STALE / partial？**
   文件是新的、`stale` 却为真，只剩两条来源：`snapshot.is_stale` 或 `partial`（`snapshot.partial` / `quality.partial`）。这时问题在采集侧，检查 bundle 里的 `collector` / `quality`（`rest_ok`、`ws_connected`、`mismatch`、`last_error`）与 `coverage`（`essential_ok`、`orders_covered`、`failures`、`essential_failures`）。

6. **区间曲线不画？**
   不是故障：少于 2 个真实快照（或当前币种下不足 2 个可用值）时前端刻意不画线，页面写的是"数据不足：该区间至少需要 2 个真实快照（不插值、不伪造）"。若 `series.json` 本身不可用，文案变为"历史数据暂不可用，未绘制曲线。"——两者的区别正好指向"采集还没攒够点"与"文件读不到"。

7. **注意别被"刚删掉文件仍显示 LIVE"误导。**
   文件在 180s 内成功读过一次时，读取器会继续供最后一次成功读取的副本（设计上的短窗兜底），此时 `stale` 按 **mtime 年龄**判定，可能短暂仍为 LIVE；窗口关闭后立刻转为 `riskbot export bundle not found`。想看真实状态，用第 2 节 b 命令看文件年龄，不要只看徽标。

> **English summary** — Troubleshoot in this order: authorization (403 / reason `forbidden`, empty allowlist denies everyone) → the literal `reason` string on the card → bundle presence and mtime age → 404-vs-401 route probe and `pm-preserve verify` when the build tree lost PM → STALE/partial with a fresh file means the collector side (`snapshot.is_stale`, `quality`, `coverage`) → a missing curve with fewer than two snapshots is intended behaviour, not a fault → and a just-deleted bundle can still read LIVE for up to 180s from `read_at`, so trust the file mtime over the badge.
