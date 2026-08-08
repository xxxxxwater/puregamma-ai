import { Database, FilePlus2, Sparkles, X } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import type { AgentAttachment, SkillSummary } from "@/lib/api";

const DATA_SOURCES = ["market", "rss", "fintwit", "x-twitter", "bloomberg", "portfolio", "options"] as const;

export function ContextControls({ locale, dataSources, skills, skillCatalog, customPrompt, attachments, allowedSources, onToggleSource, onToggleSkill, onPrompt, onRemoveFile }: { locale: Locale; dataSources: string[]; skills: string[]; skillCatalog: SkillSummary[]; customPrompt: string; attachments: AgentAttachment[]; allowedSources: string[]; onToggleSource: (value: string) => void; onToggleSkill: (value: string) => void; onPrompt: (value: string) => void; onRemoveFile: (name: string) => void }) {
  const zh = locale === "zh";
  const sourceLabels: Record<string, string> = { market: zh ? "实时行情" : "Live market", rss: "RSS", fintwit: "FinTwit", "x-twitter": "X / Twitter", bloomberg: "Bloomberg", portfolio: zh ? "账户数据" : "Portfolio", options: zh ? "期权" : "Options" };
  const skillLabels: Record<string, string> = { market_research: zh ? "市场研究" : "Market research", news_research: zh ? "新闻检索" : "News research", portfolio_review: zh ? "组合复核" : "Portfolio review", options_analysis: zh ? "期权分析" : "Options analysis", source_check: zh ? "来源核验" : "Source verification", deep_research: zh ? "深度研究" : "Deep research" };
  return <div className="space-y-6">
    <section><div className="mb-1 flex items-center gap-2 text-xs font-semibold"><Database className="h-3.5 w-3.5" />{zh ? "数据范围" : "Data scope"}<span className="ml-auto font-normal text-text-pg-dim">{dataSources.length ? (zh ? "手动" : "Manual") : "Auto"}</span></div><p className="mb-2 text-[10px] leading-4 text-text-pg-dim">{zh ? "不选择时由 Agent 根据目标自动决定。" : "When blank, the Agent selects sources from the goal."}</p><div className="grid grid-cols-2 gap-2">{DATA_SOURCES.map((item) => { const allowed = allowedSources.includes("all") || allowedSources.includes(item) || (item === "x-twitter" && allowedSources.includes("x")); return <button key={item} type="button" disabled={!allowed} onClick={() => onToggleSource(item)} title={!allowed ? (zh ? "当前套餐不可用" : "Upgrade required") : sourceLabels[item]} className={`min-h-9 border px-2 text-left text-[11px] disabled:cursor-not-allowed disabled:opacity-35  rounded-lg${dataSources.includes(item) ? "border-border-pg-strong bg-bg-panel text-text-pg" : "border-border-pg text-text-pg-dim hover:text-text-pg-muted"}`}>{sourceLabels[item]}{!allowed ? " · Locked" : ""}</button>; })}</div></section>
    <section><div className="mb-1 flex items-center gap-2 text-xs font-semibold"><Sparkles className="h-3.5 w-3.5" />{zh ? "指定 Skills" : "Pinned Skills"}<span className="ml-auto font-normal text-text-pg-dim">{skills.length ? (zh ? "手动" : "Manual") : "Auto"}</span></div><p className="mb-2 text-[10px] leading-4 text-text-pg-dim">{zh ? "仅在你需要固定研究方法时选择。" : "Select only when you need a specific research contract."}</p><div className="space-y-1.5">{skillCatalog.map((item) => <label key={item.skill_id} title={item.description} className="flex cursor-pointer items-start gap-2 border border-border-pg px-2.5 py-2 text-xs rounded-lg"><input type="checkbox" checked={skills.includes(item.skill_id)} onChange={() => onToggleSkill(item.skill_id)} className="mt-0.5 accent-[var(--foreground)]" /><span className="min-w-0 flex-1"><span className="block">{skillLabels[item.slug] || item.name}</span><span className="mt-0.5 block truncate text-[10px] text-text-pg-dim">v{item.current_version} · {item.scope} · {item.risk_level}</span></span></label>)}</div></section>
    <section><label className="mb-1 block text-xs font-semibold">{zh ? "回答偏好" : "Response preferences"}</label><p className="mb-2 text-[10px] leading-4 text-text-pg-dim">{zh ? "只控制表达方式，不改变事实、权限或风险规则。" : "Controls presentation only, not evidence, permissions, or risk rules."}</p><textarea value={customPrompt} onChange={(event) => onPrompt(event.target.value.slice(0, 2000))} rows={4} placeholder={zh ? "例如：使用简洁中文，先结论后证据，列出反方观点。" : "Example: concise answer, conclusion first, include counter-evidence."} className="w-full resize-y border border-border-pg bg-bg-panel p-2 text-xs leading-5 outline-none focus:border-border-pg-strong rounded-lg" /><div className="mt-1 text-right text-[10px] text-text-pg-dim">{customPrompt.length}/2000</div></section>
    <section><div className="mb-2 flex items-center gap-2 text-xs font-semibold"><FilePlus2 className="h-3.5 w-3.5" />{zh ? "文件" : "Files"}<span className="ml-auto font-normal text-text-pg-dim">{attachments.length}/5</span></div>{attachments.length ? <div className="space-y-1.5">{attachments.map((file) => <div key={file.name} className="flex items-center gap-2 border border-border-pg bg-bg-panel px-2 py-2 text-xs rounded-lg"><span className="min-w-0 flex-1 truncate">{file.name}</span><button type="button" onClick={() => onRemoveFile(file.name)} title={zh ? "移除" : "Remove"}><X className="h-3.5 w-3.5" /></button></div>)}</div> : <p className="text-[11px] leading-5 text-text-pg-dim">{zh ? "支持 TXT、MD、CSV、JSON；单文件 20KB，总计 50KB。" : "TXT, MD, CSV, JSON; 20KB each and 50KB total."}</p>}</section>
  </div>;
}

export function nextActionLabel(action: string, zh: boolean) {
  const labels: Record<string, [string, string]> = {
    compare_changes: ["对比后续变化", "Compare changes"], set_watch: ["加入关注", "Set a watch"], review_risk: ["检查风险", "Review risk"],
    track_catalyst: ["跟踪催化剂", "Track catalyst"], compare_sources: ["交叉核验", "Cross-check sources"], stress_test: ["压力测试", "Stress test"],
    review_concentration: ["检查集中度", "Review concentration"], schedule_brief: ["生成每日简报", "Schedule a brief"], compare_expiries: ["比较到期日", "Compare expiries"],
    review_liquidity: ["检查流动性", "Review liquidity"], save_research: ["整理研究结论", "Save research"], adjust_assumptions: ["调整假设", "Adjust assumptions"],
    compare_periods: ["比较不同周期", "Compare periods"], paper_preview: ["预览 PAPER", "Preview PAPER"], deepen_research: ["继续深挖", "Deepen research"],
  };
  return labels[action]?.[zh ? 0 : 1] || action.replaceAll("_", " ");
}

export function nextActionPrompt(action: string, zh: boolean) {
  const label = nextActionLabel(action, zh);
  return zh ? `基于刚才的研究继续：${label}。先说明需要补充的证据，再给出可执行的下一步。` : `Continue from the previous research: ${label}. State any additional evidence needed, then give the next actionable step.`;
}

export function StrategyToolResult({ result, locale }: { result: { tool: string; data: Record<string, unknown> }; locale: Locale }) {
  if (!result.tool.includes("strategy") && !result.tool.includes("activation") && !result.tool.includes("order_preview")) return null;
  const zh = locale === "zh";
  const data = result.data;
  const draft = (data.draft || (data.payload as Record<string, unknown> | undefined)?.strategy || {}) as Record<string, unknown>;
  const run = (data.run || {}) as Record<string, unknown>;
  return <section className="border border-border-pg-strong bg-bg-panel p-4 text-sm rounded-xl">
    <div className="flex items-start justify-between gap-3"><div><p className="text-xs uppercase text-text-pg-dim">{result.tool}</p><h3 className="mt-1 font-semibold">{String(data.name || (data.intent_type ? `${data.execution_mode} activation` : "Strategy control"))}</h3></div><span className="border border-border-pg px-2 py-1 text-xs rounded-lg">{String(data.status || run.status || "PREVIEW")}</span></div>
    <div className="mt-4 grid gap-3 sm:grid-cols-3"><ToolMetric label={zh ? "版本" : "Version"} value={String(data.current_version || data.strategy_version || run.strategy_version || "-")} /><ToolMetric label={zh ? "模式" : "Mode"} value={String(data.execution_mode || run.execution_mode || draft.execution_mode || "-")} /><ToolMetric label={zh ? "标的" : "Instrument"} value={Array.isArray(draft.instruments) ? draft.instruments.join(", ") : String(data.instrument || "-")} /></div>
    {Array.isArray(draft.sentiment_sources) ? <p className="mt-3 text-xs text-text-pg-muted">{zh ? "数据源" : "Sources"}: {draft.sentiment_sources.join(", ") || "market"}</p> : null}
    {data.confirmation ? <div className="mt-3 border border-status-warning bg-bg-panel-muted p-3 rounded-lg"><p className="text-xs text-status-warning">{zh ? "Runtime 尚未启动。下一轮需完整发送：" : "Runtime not started. Send this exact phrase in a new turn:"}</p><code className="mt-2 block overflow-x-auto text-xs">{String(data.confirmation)}</code></div> : null}
  </section>;
}

function ToolMetric({ label, value }: { label: string; value: string }) { return <div><p className="text-xs text-text-pg-dim">{label}</p><p className="mt-1 font-medium">{value}</p></div>; }
