"use client";

import { useEffect, useState } from "react";
import { Eye, KeyRound, Loader2, Pause, Play, RefreshCw, Settings2 } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { DataSourceStatusBadge } from "@/components/puregamma";
import type { Locale } from "@/i18n/routing";
import { checkDataSource, controlDataSource, DataSourcePreview, DataSourceRow, getDataSourcePreview, getDataSources, syncDataSource } from "@/lib/api";

const PRIMARY = ["rss", "fintwit", "x-twitter", "bloomberg"];
const primarySources = (rows: DataSourceRow[]) => rows.filter((row) => PRIMARY.includes(row.id)).sort((left, right) => PRIMARY.indexOf(left.id) - PRIMARY.indexOf(right.id));

export function DataSourceTable({ initialSources, locale }: { initialSources: DataSourceRow[]; locale: Locale; labels?: Record<string, string> }) {
  const [sources, setSources] = useState(primarySources(initialSources));
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [previewId, setPreviewId] = useState("");
  const [preview, setPreview] = useState<DataSourcePreview | null>(null);
  const zh = locale === "zh";

  useEffect(() => {
    if (sources.length) return;
    getDataSources(locale).then((result) => setSources(primarySources(result.sources))).catch((reason) => setError((reason as Error).message));
  }, [locale, sources.length]);

  const replace = (source: DataSourceRow) => setSources((rows) => rows.map((row) => row.id === source.id ? source : row));
  const act = async (id: string, action: "sync" | "toggle" | "check") => {
    setBusy(`${id}:${action}`); setError("");
    try {
      const current = sources.find((row) => row.id === id)!;
      if (action === "sync") {
        await syncDataSource(id);
        const refreshed = await getDataSources(locale);
        const row = refreshed.sources.find((item) => item.id === id);
        if (row) replace(row);
      } else if (action === "toggle") replace((await controlDataSource(id, !current.enabled)).source);
      else replace((await checkDataSource(id)).source);
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  };
  const inspect = async (id: string) => {
    if (previewId === id) { setPreviewId(""); setPreview(null); return; }
    setBusy(`${id}:preview`); setError("");
    try { setPreview(await getDataSourcePreview(id)); setPreviewId(id); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(""); }
  };

  if (!sources.length) return <div className="border border-status-warning p-4 text-sm text-status-warning rounded-xl">{zh ? "无法读取数据源状态。请确认管理员登录和 API 连接。" : "Unable to load data sources. Confirm admin authentication and API connectivity."}</div>;
  return <div className="space-y-4">
    {error ? <div className="border border-status-negative p-3 text-sm text-status-negative rounded-lg">{error}</div> : null}
    <div className="grid gap-4 lg:grid-cols-2">
      {sources.map((source) => {
        const isBusy = busy.startsWith(`${source.id}:`);
        const quota = source.quotaLimit == null ? "-" : `${source.quotaRemaining ?? 0} / ${source.quotaLimit}`;
        return <article key={source.id} className="border border-border-pg bg-bg-panel rounded-lg">
          <div className="flex items-start justify-between gap-4 border-b border-border-pg p-4">
            <div className="min-w-0"><p className="text-xs uppercase text-text-pg-dim">{source.type}</p><h2 className="mt-1 text-base font-semibold">{source.source}</h2><p className="mt-1 truncate text-xs text-text-pg-muted">{source.provider}</p></div>
            <DataSourceStatusBadge locale={locale} status={source.status} />
          </div>
          <dl className="grid grid-cols-2 gap-x-5 gap-y-4 p-4 text-sm sm:grid-cols-3">
            <Metric label={zh ? "最近同步" : "Last sync"} value={source.lastSync ? new Date(source.lastSync).toLocaleString(locale) : "-"} />
            <Metric label={zh ? "标准化条数" : "Normalized"} value={String(source.itemsIngested)} />
            <Metric label={zh ? "当前配额" : "Quota"} value={quota} />
            <Metric label={zh ? "错误次数" : "Errors"} value={String(source.errorCount ?? 0)} />
            <Metric label={zh ? "账号数量" : "Accounts"} value={source.id === "fintwit" ? String(source.accountCount ?? 0) : "-"} />
            <Metric label={zh ? "配置状态" : "Configuration"} value={source.configured ? (zh ? "已配置" : "Configured") : (zh ? "需要处理" : "Action required")} />
            <Metric label={zh ? "数据新鲜度" : "Freshness"} value={source.sourceTimestamp ? new Date(source.sourceTimestamp).toLocaleString(locale) : "-"} />
            <Metric label={zh ? "套餐权限" : "Entitlement"} value={source.entitled ? (zh ? "可用" : "Allowed") : (zh ? "需要升级" : "Upgrade required")} />
            <Metric label={zh ? "再分发" : "Redistribution"} value={source.redistributionAllowed ? (zh ? "允许" : "Allowed") : (zh ? "受限" : "Restricted")} />
          </dl>
          <div className="space-y-2 border-t border-border-pg px-4 py-3 text-xs text-text-pg-muted">
            <p className="flex gap-2"><KeyRound className="mt-0.5 h-3.5 w-3.5 shrink-0" /><span>{source.licenseStatus || "-"}</span></p>
            <p>{zh ? "保留策略" : "Retention"}: {source.retentionPolicy || "-"}</p>
            {source.error ? <p className="text-status-warning" title={source.error}>{source.error}</p> : null}
            {source.failureReason && source.failureReason !== source.error ? <p className="text-status-warning">{source.failureReason}</p> : null}
            {source.isMock ? <p className="font-semibold text-status-warning">MOCK / DEMO</p> : null}
          </div>
          <div className="flex items-center gap-2 border-t border-border-pg p-3">
            <IconButton title={zh ? "手动同步" : "Sync now"} disabled={isBusy || !source.enabled} onClick={() => act(source.id, "sync")} icon={busy === `${source.id}:sync` ? Loader2 : RefreshCw} spin={busy === `${source.id}:sync`} />
            <IconButton title={source.enabled ? (zh ? "暂停" : "Pause") : (zh ? "恢复" : "Resume")} disabled={isBusy} onClick={() => act(source.id, "toggle")} icon={source.enabled ? Pause : Play} />
            <IconButton title={zh ? "配置检查" : "Check configuration"} disabled={isBusy} onClick={() => act(source.id, "check")} icon={Settings2} />
            <IconButton title={zh ? "数据预览" : "Preview data"} disabled={isBusy} onClick={() => inspect(source.id)} icon={busy === `${source.id}:preview` ? Loader2 : Eye} spin={busy === `${source.id}:preview`} />
          </div>
          {previewId === source.id && preview ? <div className="border-t border-border-pg bg-bg-panel-muted p-4"><p className="mb-3 text-xs font-semibold uppercase text-text-pg-muted">{zh ? "最近标准化数据" : "Recent normalized data"}</p><div className="space-y-3">{preview.normalized.slice(0, 5).map((item) => <div key={item.id} className="border-l-2 border-border-pg-strong pl-3"><p className="text-sm font-medium">{item.title}</p><p className="mt-1 text-xs text-text-pg-muted">{item.sourceName} · {item.symbols.join(", ") || (zh ? "无明确资产" : "No explicit asset")} · {item.sentiment.label || "neutral"}</p>{item.url ? <a href={item.url} target="_blank" rel="noreferrer" className="mt-1 block truncate text-xs text-text-pg-dim hover:underline">{item.url}</a> : null}</div>)}{!preview.normalized.length ? <p className="text-xs text-text-pg-muted">{zh ? "暂无标准化数据" : "No normalized documents yet"}</p> : null}</div></div> : null}
        </article>;
      })}
    </div>
  </div>;
}

function Metric({ label, value }: { label: string; value: string }) { return <div className="min-w-0"><dt className="text-xs text-text-pg-dim">{label}</dt><dd className="mt-1 truncate font-medium" title={value}>{value}</dd></div>; }
function IconButton({ title, disabled, onClick, icon: Icon, spin = false }: { title: string; disabled: boolean; onClick: () => void; icon: LucideIcon; spin?: boolean }) { return <button type="button" onClick={onClick} disabled={disabled} className="grid h-9 w-9 place-items-center border border-border-pg hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-35 rounded-lg" title={title} aria-label={title}><Icon className={`h-4 w-4 ${spin ? "animate-spin" : ""}`} /></button>; }
