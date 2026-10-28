"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { ArrowUpRight, CornerUpLeft, SearchCheck, X } from "lucide-react";
import type { Locale } from "@/i18n/routing";
import type { AgentEvidenceSummary, AgentSource } from "@/lib/api";
import { sourceAgeMinutes } from "@/lib/agent-run-events";
import { useDialogFocus } from "@/lib/use-dialog-focus";

const COPY = {
  en: {
    title: "Evidence",
    close: "Close evidence",
    sufficient: "Evidence requirements met",
    gaps: (missing: string) => `Gaps: ${missing}`,
    noCheck: "No evidence check was recorded for this answer.",
    sources: (n: number) => `${n} source${n === 1 ? "" : "s"}`,
    none: "This answer cites no sources.",
    published: "Published",
    fetched: "Fetched",
    age: (minutes: number) => (minutes < 60 ? `${minutes} min old` : minutes < 2880 ? `${Math.round(minutes / 60)} h old` : `${Math.round(minutes / 1440)} d old`),
    unknownTime: "time unknown",
    stale: "May be stale",
    back: "Back to the answer",
    open: "Open source",
  },
  zh: {
    title: "证据",
    close: "关闭证据",
    sufficient: "证据检查通过",
    gaps: (missing: string) => `缺口：${missing}`,
    noCheck: "此回答没有记录证据检查。",
    sources: (n: number) => `${n} 条来源`,
    none: "此回答没有引用来源。",
    published: "发布",
    fetched: "抓取",
    age: (minutes: number) => (minutes < 60 ? `${minutes} 分钟前` : minutes < 2880 ? `${Math.round(minutes / 60)} 小时前` : `${Math.round(minutes / 1440)} 天前`),
    unknownTime: "时间未知",
    stale: "可能已过时",
    back: "回到回答",
    open: "打开来源",
  },
};

/** Sources older than this are flagged; market context goes stale fast. */
const STALE_MINUTES = 24 * 60;

/**
 * On-demand evidence for one answer: the server's evidence check, then each
 * cited source with provider, publication and fetch times and its age. Opened
 * from a citation marker or the answer's source count; it overlays the
 * transcript instead of permanently narrowing it, and returns focus to where
 * it was opened from.
 */
export function EvidenceInspector({ locale, messageId, sources, evidence, focus, onClose }: { locale: Locale; messageId: string; sources: AgentSource[]; evidence?: AgentEvidenceSummary | null; focus?: number; onClose: () => void }) {
  const copy = COPY[locale === "zh" ? "zh" : "en"];
  const panelRef = useRef<HTMLDivElement | null>(null);
  const closeRef = useRef<HTMLButtonElement | null>(null);


  // Rendered into <body>: inside the chat card it inherited that card's
  // stacking context and slid under the app header.
  const [host, setHost] = useState<HTMLElement | null>(null);
  useEffect(() => setHost(document.body), []);
  // Focus handling starts once the portal (and so the panel) exists.
  useDialogFocus(host !== null, panelRef, onClose, closeRef);
  useEffect(() => {
    if (focus == null || !host) return;
    const target = panelRef.current?.querySelector<HTMLElement>(`[data-citation-index="${focus}"]`);
    if (target) {
      target.scrollIntoView({ block: "nearest" });
      target.focus();
    }
  }, [focus, host]);

  const ordered = [...sources].sort((a, b) => a.citation_index - b.citation_index);
  const backToAnswer = (index: number) => {
    onClose();
    window.setTimeout(() => {
      const marker = document.querySelector<HTMLElement>(`[href="#cite-${messageId}-${index}"]`) || document.getElementById(`message-${messageId}`);
      marker?.scrollIntoView({ block: "center" });
      marker?.focus();
    }, 0);
  };

  if (!host) return null;
  return createPortal(
    <>
      <div className="fixed inset-0 z-[60] bg-black/40" aria-hidden onClick={onClose} />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="evidence-inspector-title"
        data-testid="evidence-inspector"
        className="fixed inset-y-0 right-0 z-[61] flex w-[min(26rem,100vw)] flex-col border-l border-border-pg shadow-2xl"
        // Opaque page surface on purpose: the glass skin makes panels
        // translucent, and evidence must never be read through the answer.
        style={{ paddingBottom: "env(safe-area-inset-bottom)", background: "var(--pg-bg-page)" }}
      >
        <div className="flex items-center justify-between gap-2 border-b border-border-pg p-4">
          <h2 id="evidence-inspector-title" className="flex items-center gap-2 text-sm font-semibold"><SearchCheck className="h-4 w-4" aria-hidden />{copy.title} · {copy.sources(ordered.length)}</h2>
          <button ref={closeRef} type="button" onClick={onClose} aria-label={copy.close} className="grid h-9 w-9 place-items-center rounded-lg hover:bg-[var(--pg-surface-hover)]"><X className="h-4 w-4" /></button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto p-4 text-sm">
          <p className={`rounded-lg px-3 py-2 text-xs ${evidence ? (evidence.sufficient ? "bg-[var(--pg-surface-2)] text-text-pg-muted" : "bg-[var(--pg-warning-soft,var(--pg-surface-2))] text-status-warning") : "bg-[var(--pg-surface-2)] text-text-pg-dim"}`} data-testid="evidence-status">
            {evidence ? (evidence.sufficient ? copy.sufficient : copy.gaps(evidence.missing.join(", "))) : copy.noCheck}
          </p>
          {ordered.length === 0 ? <p className="mt-4 text-text-pg-dim">{copy.none}</p> : null}
          <ol className="mt-4 space-y-3">
            {ordered.map((source) => {
              const reference = source.published_at || source.source_timestamp || source.fetched_at;
              const age = sourceAgeMinutes(reference);
              const stale = age !== null && age > STALE_MINUTES;
              return (
                <li key={`${source.citation_index}-${source.title}`} id={`source-${messageId}-${source.citation_index}`} data-citation-index={source.citation_index} tabIndex={-1} className="rounded-lg border border-border-pg p-3 outline-none focus-visible:ring-2 focus-visible:ring-[var(--pg-focus-ring)]">
                  <div className="flex items-start gap-2">
                    <span className="mt-0.5 shrink-0 font-mono text-xs text-text-pg-dim">[{source.citation_index}]</span>
                    <div className="min-w-0 flex-1">
                      <p className="break-words font-medium leading-5">{source.title}</p>
                      <p className="mt-1 text-xs text-text-pg-dim">{source.provider}</p>
                      <dl className="mt-2 grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 gap-y-0.5 text-xs text-text-pg-muted">
                        <dt>{copy.published}</dt><dd>{source.published_at ? new Date(source.published_at).toLocaleString(locale) : copy.unknownTime}</dd>
                        <dt>{copy.fetched}</dt><dd>{source.fetched_at ? new Date(source.fetched_at).toLocaleString(locale) : copy.unknownTime}</dd>
                      </dl>
                      <p className={`mt-1 text-xs ${stale ? "text-status-warning" : "text-text-pg-dim"}`}>{age === null ? copy.unknownTime : copy.age(age)}{stale ? ` · ${copy.stale}` : ""}</p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        <button type="button" onClick={() => backToAnswer(source.citation_index)} className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-xs text-text-pg-muted hover:bg-[var(--pg-surface-hover)]"><CornerUpLeft className="h-3 w-3" aria-hidden />{copy.back}</button>
                        {source.url ? <a href={source.url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-8 items-center gap-1 rounded-md px-2 text-xs text-accent hover:bg-[var(--pg-surface-hover)]">{copy.open}<ArrowUpRight className="h-3 w-3" aria-hidden /></a> : null}
                      </div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ol>
        </div>
      </aside>
    </>,
    host,
  );
}
