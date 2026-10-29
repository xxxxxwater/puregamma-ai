import { Boxes, Sparkles } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import type { AgentPluginEntry, SkillSummary } from "@/lib/api";

/**
 * Response preferences and files - and nothing else.
 *
 * The data-source grid and the skill picker are gone on purpose. Capabilities
 * are built-in plugins (the Agent chooses its sources and tools from the goal),
 * so a per-message switch is a way to configure a worse answer, not a feature.
 * See docs/architecture/DSH_0_1_7_RC1_AGENT_SKILL_NAVPM_UPGRADE.md.
 */
export function ContextControls({ locale, plugins, pluginCounts, skills = [], customPrompt, onPrompt }: { locale: Locale; plugins: AgentPluginEntry[]; pluginCounts: { total: number; enabled: number; tools: number } | null; skills?: SkillSummary[]; customPrompt: string; onPrompt: (value: string) => void }) {
  const zh = locale === "zh";
  return <div className="space-y-6">
    {/* Built-in capabilities. Read-only on purpose: capability is installed by
        the platform, not toggled per message, so there is nothing here for a
        user to switch off into a worse answer. */}
    <section data-testid="agent-plugins">
      <div className="mb-1 flex items-center gap-2 text-xs font-semibold"><Boxes className="h-3.5 w-3.5" />{zh ? "内置插件" : "Built-in plugins"}<span className="ml-auto font-normal text-text-pg-dim">{pluginCounts ? `${pluginCounts.enabled}/${pluginCounts.total} · ${pluginCounts.tools} ${zh ? "工具" : "tools"}` : "--"}</span></div>
      <p className="mb-2 text-11 leading-4 text-text-pg-dim">{zh ? "能力由平台内置插件提供，Agent 根据目标自行调用；不需要在每条消息里选择。" : "Capabilities come from built-in plugins and the Agent picks what to call from the goal; nothing is selected per message."}</p>
      <div className="space-y-1.5">{plugins.map((plugin) => <div key={plugin.id} className="border border-border-pg px-2.5 py-2 text-xs rounded-lg">
        <div className="flex items-center gap-2"><span className="min-w-0 flex-1 truncate">{plugin.name}</span><span className={`shrink-0 border px-1.5 py-0.5 text-11 rounded-lg ${plugin.enabled ? "border-status-positive text-status-positive" : "border-border-pg text-text-pg-dim"}`}>{plugin.enabled ? (zh ? "已启用" : "Enabled") : (plugin.reason === "plan_required" ? (zh ? "套餐不含" : "Plan") : (zh ? "不可用" : "Unavailable"))}</span></div>
        <span className="mt-1 block leading-4 text-text-pg-dim">{plugin.description}</span>
        <span className="mt-1 block truncate font-mono text-11 text-text-pg-dim">{plugin.service}{plugin.tools.length ? ` · ${plugin.tools.length} ${zh ? "个工具" : "tools"}` : ""}</span>
      </div>)}</div>
    </section>
    {skills.length ? <SkillList locale={locale} skills={skills} /> : null}
    <section><label className="mb-1 block text-xs font-semibold">{zh ? "回答偏好" : "Response preferences"}</label><p className="mb-2 text-11 leading-4 text-text-pg-dim">{zh ? "只控制表达方式，不改变事实、权限或风险规则。" : "Controls presentation only, not evidence, permissions, or risk rules."}</p><textarea value={customPrompt} onChange={(event) => onPrompt(event.target.value.slice(0, 2000))} rows={4} placeholder={zh ? "例如：使用简洁中文，先结论后证据，列出反方观点。" : "Example: concise answer, conclusion first, include counter-evidence."} className="w-full resize-y border border-border-pg bg-bg-panel p-2 text-xs leading-5 outline-none focus:border-border-pg-strong rounded-lg" /><div className="mt-1 text-right text-11 text-text-pg-dim">{customPrompt.length}/2000</div></section>
  </div>;
}

/** Why a skill is not in use, from the server's own fields. */
function skillUnavailableReason(skill: SkillSummary, zh: boolean): string | null {
  if (skill.status !== "published") return zh ? "审核中，尚未发布" : "In review, not published";
  if (!skill.installed) return zh ? "未安装" : "Not installed";
  if (!skill.enabled) return zh ? "已停用" : "Disabled";
  return null;
}

/**
 * Skills the Agent may load, read-only. The Agent picks them from the goal;
 * what this shows is what each is for, which tools it is limited to, and why
 * one is unavailable. A Skill's text never grants a tool permission.
 */
function SkillList({ locale, skills }: { locale: Locale; skills: SkillSummary[] }) {
  const zh = locale === "zh";
  const ready = skills.filter((skill) => !skillUnavailableReason(skill, zh)).length;
  return <section data-testid="agent-skills">
    <div className="mb-1 flex items-center gap-2 text-xs font-semibold"><Sparkles className="h-3.5 w-3.5" />Skills<span className="ml-auto font-normal text-text-pg-dim">{ready}/{skills.length} {zh ? "可用" : "available"}</span></div>
    <p className="mb-2 text-11 leading-4 text-text-pg-dim">{zh ? "Agent 按目标自动选用；Skill 说明不会提升任何工具权限，工具仍受账户、套餐与审批限制。" : "The Agent picks these from the goal. A Skill's instructions never raise a tool permission; tools stay bound by account, plan and approval."}</p>
    <ul className="space-y-1.5">{skills.map((skill) => {
      const reason = skillUnavailableReason(skill, zh);
      return <li key={skill.skill_id} className="rounded-lg border border-border-pg px-2.5 py-2 text-xs">
        <div className="flex items-center gap-2"><span className="min-w-0 flex-1 truncate font-medium">{skill.name}</span><span className={`shrink-0 rounded-lg border px-1.5 py-0.5 text-11 ${reason ? "border-border-pg text-text-pg-dim" : "border-status-positive text-status-positive"}`}>{reason ?? (zh ? "可用" : "Available")}</span></div>
        <span className="mt-1 block leading-4 text-text-pg-dim">{skill.description}</span>
        {skill.tool_allowlist?.length ? <span className="mt-1 block break-words font-mono text-11 text-text-pg-dim">{zh ? "可用工具" : "Tools"}: {skill.tool_allowlist.join(", ")}</span> : null}
        {skill.runtime?.human_confirmation_required ? <span className="mt-1 block text-11 text-status-warning">{zh ? "执行前需要你的确认" : "Needs your confirmation before acting"}</span> : null}
      </li>;
    })}</ul>
  </section>;
}

export function nextActionLabel(action: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    compare_changes: ["对比后续变化", "Compare changes"], set_watch: ["加入关注", "Set a watch"], review_risk: ["检查风险", "Review risk"],
    track_catalyst: ["跟踪催化剂", "Track catalyst"], compare_sources: ["交叉核验", "Cross-check sources"], stress_test: ["压力测试", "Stress test"],
    review_concentration: ["检查集中度", "Review concentration"], schedule_brief: ["生成每日简报", "Schedule a brief"], compare_expiries: ["比较到期日", "Compare expiries"],
    review_liquidity: ["检查流动性", "Review liquidity"], save_research: ["整理研究结论", "Save research"], adjust_assumptions: ["调整假设", "Adjust assumptions"],
    compare_periods: ["比较不同周期", "Compare periods"], paper_preview: ["预览 PAPER", "Preview PAPER"], deepen_research: ["继续深挖", "Deepen research"],
    review_dream_tree: ["查看 Dream Tree", "Review Dream Tree"], compare_candidate: ["比较候选策略", "Compare candidates"],
  };
  return labels[action]?.[zh ? 0 : 1] || action.replaceAll("_", " ");
}

export function nextActionPrompt(action: string, zh: boolean) {
  const label = nextActionLabel(action, zh);
  return zh ? `基于刚才的研究继续：${label}。先说明需要补充的证据，再给出可执行的下一步。` : `Continue from the previous research: ${label}. State any additional evidence needed, then give the next actionable step.`;
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function numeric(value: unknown, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function DreamRsiToolResult({ data, locale }: { data: Record<string, unknown>; locale: Locale }) {
  const zh = locale === "zh";
  const goal = asRecord(data.goal);
  const best = asRecord(data.best_candidate);
  const metrics = asRecord(best.metrics);
  const params = asRecord(best.params);
  const bestFamily = String(best.family || params.family || "-");
  const bestVariant = String(best.factor_variant || params.factor_variant || "-");
  const parameterText = Object.entries(params)
    .filter(([key]) => !["family", "factor_variant", "lookback_days", "timeframe"].includes(key))
    .slice(0, 5)
    .map(([key, value]) => `${key.replaceAll("_", " ")} ${String(value)}`)
    .join(" · ");
  const coverage = asRecord(data.data);
  const compute = asRecord(data.compute);
  const replay = asRecord(data.history_replay);
  const tree = asRecord(data.discovery_tree);
  const nodes = Array.isArray(tree.nodes) ? tree.nodes : [];
  const families = Array.isArray(tree.families) ? tree.families : [];
  const sharpe = numeric(metrics.sharpe_ratio);
  const maxDrawdown = Math.abs(numeric(metrics.max_drawdown)) * 100;
  const totalReturn = numeric(metrics.total_return) * 100;
  const coveragePct = numeric(coverage.coverage_ratio) * 100;
  const status = String(data.status || "best_effort");
  const matched = status === "constraint_satisfied" && Boolean(best.meets_constraints) && Boolean(coverage.coverage_verified);
  const targetSharpe = goal.min_sharpe == null ? "-" : `≥ ${numeric(goal.min_sharpe).toFixed(2)}`;
  const targetDrawdown = goal.max_drawdown_pct == null ? "-" : `< ${numeric(goal.max_drawdown_pct).toFixed(1)}%`;

  return <section className="mt-3 border border-border-pg-strong bg-bg-panel p-4 text-sm rounded-xl" data-testid="dream-rsi-result">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p className="text-11 uppercase tracking-[0.14em] text-text-pg-dim">Dream-RSI Control Plane</p>
        <h3 className="mt-1 font-semibold">{String(goal.symbol || "-")} · {String(goal.timeframe || "-")} {zh ? "策略发现" : "strategy discovery"}</h3>
        <p className="mt-1 text-xs text-text-pg-muted">{zh ? "历史探索树作为 replay world；仅研究，不创建订单。" : "The observed discovery tree is the replay world; research-only, no orders."}</p>
      </div>
      <span className={`border px-2 py-1 text-xs rounded-lg ${matched ? "border-status-positive text-status-positive" : "border-border-pg text-text-pg-muted"}`}>{status.replaceAll("_", " ")}</span>
    </div>
    <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <ToolMetric label={zh ? "OOS Sharpe" : "OOS Sharpe"} value={sharpe.toFixed(2)} />
      <ToolMetric label={zh ? "OOS 最大回撤" : "OOS max drawdown"} value={`${maxDrawdown.toFixed(2)}%`} />
      <ToolMetric label={zh ? "总收益" : "Total return"} value={`${totalReturn.toFixed(2)}%`} />
      <ToolMetric label={zh ? "数据覆盖" : "Coverage"} value={`${coveragePct.toFixed(1)}%`} />
    </div>
    <div className="mt-3 grid gap-2 text-xs sm:grid-cols-2">
      <div className="bg-bg-panel-muted p-2.5 rounded-lg"><span className="text-text-pg-dim">{zh ? "目标约束" : "Goal constraints"}</span><p className="mt-1">Sharpe {targetSharpe} · MaxDD {targetDrawdown}</p></div>
      <div className="bg-bg-panel-muted p-2.5 rounded-lg"><span className="text-text-pg-dim">{zh ? "最佳策略家族" : "Best strategy family"}</span><p className="mt-1">{bestFamily.replaceAll("_", " ")} · {bestVariant.replaceAll("_", " ")}</p><p className="mt-1 text-text-pg-dim">{parameterText || "-"}</p></div>
    </div>
    <div className="mt-3 flex flex-wrap gap-2 text-11 text-text-pg-muted">
      <span className="px-2 py-1 rounded-lg bg-bg-panel-muted">{zh ? "探索" : "Evaluations"} {String(compute.evaluations ?? nodes.length)}</span>
      <span className="px-2 py-1 rounded-lg bg-bg-panel-muted">{zh ? "代数" : "Generations"} {String(compute.generations ?? "-")}</span>
      <span className="px-2 py-1 rounded-lg bg-bg-panel-muted">Replay · {String(replay.selected_policy || "-")}</span>
      <span className="px-2 py-1 rounded-lg bg-bg-panel-muted">{String(coverage.data_freshness || "unknown")}</span>
      <span className="px-2 py-1 rounded-lg bg-bg-panel-muted">{zh ? "约束口径" : "Constraint basis"} · OOS</span>
    </div>
    <details className="mt-3 border-t border-border-pg pt-3 text-xs">
      <summary className="cursor-pointer text-text-pg-muted">{zh ? `查看 Family Budget 与 Discovery Tree（${nodes.length} 个节点）` : `View family budget and Discovery Tree (${nodes.length} nodes)`}</summary>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {families.map((raw, index) => {
          const family = asRecord(raw);
          return <div key={String(family.id || index)} className="p-2 rounded-lg bg-bg-panel-muted">
            <div className="flex items-center justify-between gap-2"><span className="font-medium">{String(family.label || family.family || "-")}</span><span className="font-mono text-11">budget {String(family.generation_1_budget ?? 0)}</span></div>
            <p className="mt-1 text-text-pg-dim">{String(family.status || "-")} · {String(family.evaluations ?? 0)} eval</p>
          </div>;
        })}
      </div>
      <div className="mt-2 grid gap-2 sm:grid-cols-2">
        {nodes.slice(0, 8).map((raw, index) => {
          const node = asRecord(raw);
          const nodeMetrics = asRecord(node.metrics);
          return <div key={String(node.id || index)} className="bg-bg-panel-muted p-2 rounded-lg">
            <div className="flex items-center justify-between gap-2"><span className="font-mono text-11">{String(node.id || `node-${index + 1}`)}</span><span>{Boolean(node.meets_constraints) ? "✓" : "·"}</span></div>
            <p className="mt-1">{String(node.family || "-").replaceAll("_", " ")} · {String(node.factor_variant || "-").replaceAll("_", " ")}</p>
            <p className="mt-1">S {numeric(nodeMetrics.sharpe_ratio).toFixed(2)} · DD {(Math.abs(numeric(nodeMetrics.max_drawdown)) * 100).toFixed(1)}%</p>
            <p className="mt-1 text-text-pg-dim">{String(node.factor_quality || "-")} · score {numeric(node.score).toFixed(2)}</p>
          </div>;
        })}
      </div>
    </details>
  </section>;
}
export function StrategyToolResult({ result, locale }: { result: { tool: string; data: Record<string, unknown> }; locale: Locale }) {
  if (result.tool === "run_dream_strategy_search") return <DreamRsiToolResult data={result.data} locale={locale} />;
  if (!result.tool.includes("strategy") && !result.tool.includes("activation") && !result.tool.includes("order_preview")) return null;
  const zh = locale === "zh";
  const data = result.data;
  const draft = (data.draft || (data.payload as Record<string, unknown> | undefined)?.strategy || {}) as Record<string, unknown>;
  const run = (data.run || {}) as Record<string, unknown>;
  return <section className="border border-border-pg-strong bg-bg-panel p-4 text-sm rounded-xl">
    <div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase text-text-pg-dim">{result.tool}</p><h3 className="mt-1 font-semibold">{String(data.name || (data.intent_type ? `${data.execution_mode} activation` : "Strategy control"))}</h3></div><span className="px-2 py-1 text-xs rounded-lg bg-bg-panel-muted">{String(data.status || run.status || "PREVIEW")}</span></div>
    <div className="mt-4 grid gap-3 sm:grid-cols-3"><ToolMetric label={zh ? "版本" : "Version"} value={String(data.current_version || data.strategy_version || run.strategy_version || "-")} /><ToolMetric label={zh ? "模式" : "Mode"} value={String(data.execution_mode || run.execution_mode || draft.execution_mode || "-")} /><ToolMetric label={zh ? "标的" : "Instrument"} value={Array.isArray(draft.instruments) ? draft.instruments.join(", ") : String(data.instrument || "-")} /></div>
    {Array.isArray(draft.sentiment_sources) ? <p className="mt-3 text-xs text-text-pg-muted">{zh ? "数据源" : "Sources"}: {draft.sentiment_sources.join(", ") || "market"}</p> : null}
    {data.confirmation ? <div className="mt-3 border border-status-warning bg-bg-panel-muted p-3 rounded-lg"><p className="text-xs text-status-warning">{zh ? "Runtime 尚未启动。下一轮需完整发送：" : "Runtime not started. Send this exact phrase in a new turn:"}</p><code className="mt-2 block overflow-x-auto text-xs">{String(data.confirmation)}</code></div> : null}
  </section>;
}

function ToolMetric({ label, value }: { label: string; value: string }) { return <div><p className="text-xs text-text-pg-dim">{label}</p><p className="mt-1 font-medium">{value}</p></div>; }
