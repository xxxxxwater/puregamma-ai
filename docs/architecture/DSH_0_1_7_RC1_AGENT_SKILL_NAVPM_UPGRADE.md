# PureGamma Agent / Skill / NAV PM 升级设计（DSH dsh-v0.1.7-rc.1）

日期：2026-09-24  
状态：代码升级阶段；**禁止生产部署、生产迁移、生产重启**

## 1. 固定上游

- DeepSeek Harness tag：`dsh-v0.1.7-rc.1`
- upstream commit：`46a7f68b0922371ce7144b668b90e377d8e799f4`
- PureGamma 的 `vendor/deepseek-harness` gitlink、`.gitmodules` 与 CI 必须共同锁定该版本。
- 不再以可漂移的 fork `master` 作为版本契约。

## 2. 三处现状与边界

只读核对生产机：

- API / Web 当前镜像：`harness-20260921b`；
- worker / scheduler 仍为旧 `0dbe7b48`；
- `/puregamma/build-harness-20260921/.deployed-commit` 为 `12ca171`；
- `/puregamma/app/.git` 指向已不存在的 macOS worktree 路径，因此生产目录不能当作可靠 Git 工作区；
- GitHub `main` 已明显领先生产构建。

结论：生产服务器只作为代码/行为核对基准。本任务不修服务器 Git 元数据、不改文件、不迁移数据库、不重启、不部署。

## 3. Agent 会话架构

新 Agent 对话采用固定 DSH Web 的原生 Session / Session Controller / projection / reconnect / archive / attachment / tool-view 机制。PureGamma profile 只负责品牌、认证桥、业务服务和安全边界，不 fork DSH 会话协议。

| 用户能力 | 实现归属 |
| --- | --- |
| 创建、继续、历史、归档、刷新恢复 | DSH Session |
| 流式响应、断线重连 | DSH Session Controller / transport |
| 附件 | DSH attachment / session reference |
| 工具过程显示 | DSH tool call events / tool views |
| Skill | DSH `ctx.skills` + `dsh-skill-filesystem` + `dsh-tool-skill` + `ui-skill` |
| 登录、用户隔离、模型、用量 | PureGamma provider/plugins |
| 旧 SQL Chat / Skill 历史 | 保留兼容读取；本任务不执行生产数据迁移 |

旧会话不删除。部署切流前先验证旧会话兼容读取；若以后需要物理迁移，应在数据库副本上执行独立、可重复的迁移，不在此代码升级任务执行。

## 4. Skill 机制迁移

Agent Chat 不再挂载：

- `@puregamma/dsh-skills-legacy-api`
- `@puregamma/dsh-tool-skills`
- Python `SkillRegistry` 作为 Agent Skill 发现/调用核心

Agent Chat 改用 DSH 原生：

- host + per-scope layered `ctx.skills`;
- `@deepseek-ai/dsh-skill-filesystem`;
- `@deepseek-ai/dsh-tool-skill`;
- DSH Web `/skill-name` 选择器与 Skill tool-view。

旧数据库中的 Skill / SkillVersion / SkillInstallation / SkillRun 不删除，旧 API 暂时保留供非 Agent 业务和历史审计读取。旧下划线 slug 用纯函数映射到 DSH kebab-case，例如 `market_research -> market-research`；映射代码本身不读写生产数据库。

## 5. 多用户网站权限边界

DSH upstream 的 `standard` 是 coding-agent preset，默认包含 Bash/Pwsh、任意文件读写、后台 Job、delegation 等。它不能直接作为 PureGamma 多用户网站默认权限。

PureGamma profile 对该 preset 做完整覆盖：

- 不挂载 shell / pwsh；
- 不挂载任意 `tool-fs` / `tool-fs-search`；
- 不挂载 background jobs；
- 不挂载 plugin-manager；
- 不挂载 subagent / workflow / ralph；
- Skill filesystem 使用 `includeDefaultRoots=false`；
- 只扫描受控 bundled Skill 目录；
- Skill 文本不能提升工具权限；
- 业务工具继续由 PureGamma 的 auth / entitlement / approval / risk gate 控制。

这样普通用户不会因 UI 升级获得生产服务器高权限。

## 6. NAV PM 口径与错误根因

可信数据源是 riskbot 的只读 export bundle，PureGamma Web/API 不持有该 PM 账户的交易密钥。

本次确认的金额问题属于 **UI 语义漂移**：

1. 历史 NAV series 的稳定字段是 `equity_usd`，语义为 Binance `accountEquity`；
2. 页面后续把 headline / curve 改成可选的 `adjusted_equity_usd / actualEquity`；
3. 当前生产只读 bundle 中 `actual_equity_usd` 可以为空，因此它不是稳定的 headline 数据契约；
4. headline 与 curve 应统一恢复为 `accountEquity`；
5. adjusted equity、逐币种“市值 - 负债”、BTC 钱包真实数量均保留为不同口径的诊断项，不得互换标签。

授权仍由服务端 `PM_ACCOUNT_ALLOWED_EMAILS` fail-closed allowlist 控制。生产当前只读核对为 **3 个条目**。具体邮箱不提交到公开仓库。

本修复不修改真实财务记录。

## 7. 验证要求

代码合并前：

- gitlink 必须等于 DSH 固定 commit；
- CI 必须验证固定 commit；
- Harness typecheck/build 必须通过；
- profile 中不得重新挂回 legacy Agent Skill provider；
- profile 中普通 preset 不得包含 shell/fs/job/plugin-manager/subagent；
- bundled Skill 名称必须满足 DSH kebab-case；
- PM UI headline 与历史曲线必须读取同一 `accountEquity` 口径；
- API 未授权账户保持 403；
- PM feed 继续只读且缺值时不得伪造 0。

## 8. 未来生产部署步骤（本任务不执行）

1. 记录现网镜像、配置与数据库版本并备份；
2. 构建固定 DSH submodule 的新 Harness；
3. 在隔离环境设置 `PUREGAMMA_DSH_SKILL_DIR` 并检查 Skill catalog；
4. 用非生产 DB 副本验证旧会话/历史读取；
5. 对三个 allowlist 用户逐一验证 PM 页面，其他用户验证 403；
6. 验证 headline 与 history 最后一笔的 `equity_usd` 同口径；
7. 若有 schema migration，另行审核并在维护窗口执行；
8. canary 验证 session create/send/stream/reconnect/archive/attachment/tool/Skill/error；
9. 完成监控与回滚检查后才切流；
10. worker / scheduler 与 API / Web 的版本差异需在部署计划中单独消除。

**本任务完成时生产环境仍运行原版本，新代码尚未部署。**
