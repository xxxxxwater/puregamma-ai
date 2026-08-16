"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Link as LinkIcon } from "lucide-react";
import { CapabilityGate, useCapabilityGate } from "@/components/ocean/capability-gate";
import { EvidenceGraph, type EvidenceNode } from "@/components/ocean/evidence-graph";
import { OceanShell } from "@/components/ocean/ocean-shell";
import { ResearchTimeline, stagesForStatus } from "@/components/ocean/research-timeline";
import { StatusBadgeWithPulse } from "@/components/ocean/status-badge";
import { getResearchRun, getResearchRunArtifacts, getResearchRunEvidence, type HarnessResearchRun } from "@/lib/api";
import { OCEAN_POLL_INTERVAL_ACTIVE_MS, OCEAN_POLL_INTERVAL_IDLE_MS } from "@/lib/ocean";
import { type Locale, withLocale } from "@/i18n/routing";

const ACTIVE_STATUSES = new Set(["queued", "preparing", "running", "validating"]);

type ConnectionMode = "sse" | "polling";

function formatTime(value: string | null | undefined, locale: string) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(locale, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

function formatDuration(from: string, to: string, locale: "en" | "zh") {
  const start = new Date(from).getTime();
  const end = new Date(to).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return "-";
  const minutes = Math.max(0, Math.round((end - start) / 60_000));
  if (minutes < 1) return locale === "zh" ? "<1 分钟" : "<1 min";
  return locale === "zh" ? `${minutes} 分钟` : `${minutes} min`;
}

export function ResearchRunDetail({ locale, runId }: { locale: Locale; runId: string }) {
  const zh = locale === "zh";
  const load = useCallback(() => getResearchRun(runId), [runId]);
  const { state, retry } = useCapabilityGate(load, [runId]);
  const [run, setRun] = useState<HarnessResearchRun | null>(null);
  const [evidenceNodes, setEvidenceNodes] = useState<EvidenceNode[]>([]);
  const [artifacts, setArtifacts] = useState<{ id: string; type: string; title: string; url?: string | null }[]>([]);
  const [connectionMode, setConnectionMode] = useState<ConnectionMode>("sse");
  const sseControllerRef = useRef<AbortController | null>(null);
  const runRef = useRef<HarnessResearchRun | null>(null);
  runRef.current = run;

  const applyRun = useCallback((payload: { run?: HarnessResearchRun } | HarnessResearchRun | null) => {
    const next = (payload as { run?: HarnessResearchRun })?.run ?? (payload as HarnessResearchRun | null);
    if (next) setRun(next);
  }, []);

  // Polling loop: authoritative server state. Connection trouble NEVER marks
  // the run failed — the server-side status always wins.
  useEffect(() => {
    if (state.status !== "available") return;
    let disposed = false;
    let timer = 0;
    const poll = async () => {
      try {
        const payload = await getResearchRun(runId);
        if (disposed) return;
        applyRun(payload);
        timer = window.setTimeout(poll, ACTIVE_STATUSES.has(payload.run.status) ? OCEAN_POLL_INTERVAL_ACTIVE_MS : OCEAN_POLL_INTERVAL_IDLE_MS);
      } catch {
        if (disposed) return;
        setConnectionMode("polling");
        timer = window.setTimeout(poll, OCEAN_POLL_INTERVAL_IDLE_MS);
      }
    };
    void poll();
    return () => {
      disposed = true;
      window.clearTimeout(timer);
    };
  }, [state.status, runId, applyRun]);

  // SSE stream (frozen contract). Connected once per run while active.
  // Unknown events are ignored; disconnects fall back to polling silently.
  useEffect(() => {
    if (state.status !== "available") return;
    const runStatus = run?.status;
    if (!runStatus || !ACTIVE_STATUSES.has(runStatus)) return;
    const controller = new AbortController();
    sseControllerRef.current = controller;
    let settled = false;
    const finish = () => {
      settled = true;
      setConnectionMode("polling");
      controller.abort();
    };
    const idleTimeout = window.setTimeout(finish, 20_000);
    (async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/research/runs/${encodeURIComponent(runId)}/events`, {
          credentials: "include",
          headers: { Accept: "text/event-stream" },
          signal: controller.signal,
        });
        if (!response.ok || !response.body) {
          finish();
          return;
        }
        setConnectionMode("sse");
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        while (!settled) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          let boundary = buffer.indexOf("\n\n");
          while (boundary >= 0 && !settled) {
            const block = buffer.slice(0, boundary);
            buffer = buffer.slice(boundary + 2);
            boundary = buffer.indexOf("\n\n");
            let eventName = "message";
            let dataText = "";
            for (const line of block.split("\n")) {
              if (line.startsWith("event:")) eventName = line.slice(6).trim();
              else if (line.startsWith("data:")) dataText += line.slice(5).trim();
            }
            if (!dataText) continue;
            // Unknown events are ignored — never crash on a new event type.
            if (!["run.queued", "run.state", "run.progress", "run.evidence", "run.completed", "run.failed", "run.canceled"].includes(eventName)) continue;
            try {
              const data = JSON.parse(dataText) as { status?: string; updated_at?: string; message?: string };
              if (eventName === "run.state" && data.status) {
                setRun((current) => (current ? { ...current, status: data.status as string, updated_at: data.updated_at || current.updated_at } : current));
                window.clearTimeout(idleTimeout);
              } else if (eventName === "run.completed") {
                const payload = await getResearchRun(runId).catch(() => null);
                if (payload) applyRun(payload);
                else setRun((current) => (current ? { ...current, status: "completed" } : current));
                finish();
              } else if (eventName === "run.failed") {
                setRun((current) => (current ? { ...current, status: "failed", error_message: String(data.message ?? current.error_message ?? "") } : current));
                finish();
              } else if (eventName === "run.canceled") {
                setRun((current) => (current ? { ...current, status: "canceled" } : current));
                finish();
              }
            } catch { /* malformed payload: ignore */ }
          }
        }
      } catch {
        setConnectionMode("polling");
      }
    })();
    return () => {
      settled = true;
      window.clearTimeout(idleTimeout);
      controller.abort();
      sseControllerRef.current = null;
    };
  }, [state.status, runId, run?.status, applyRun]);

  useEffect(() => {
    if (state.status !== "available") return;
    const current = runRef.current;
    if (!current) return;
    let cancelled = false;
    getResearchRunEvidence(runId)
      .then((payload) => {
        if (cancelled) return;
        const nodes: EvidenceNode[] = [];
        const byScope = new Map<string, { count: number; first: (typeof payload.evidence)[number] | undefined }>();
        for (const item of payload.evidence || []) {
          const scope = item.source_scope || item.provider || "source";
          const entry = byScope.get(scope) || { count: 0, first: undefined };
          entry.count += 1;
          if (!entry.first) entry.first = item;
          byScope.set(scope, entry);
        }
        for (const [scope, entry] of byScope) {
          nodes.push({ id: `source-${scope}`, kind: "source", label: scope, count: entry.count, detail: entry.first?.provider ?? undefined });
        }
        const evidence = payload.evidence || [];
        nodes.push({ id: "evidence-snapshots", kind: "evidence", label: zh ? "已采集证据" : "Evidence snapshots", count: evidence.length, status: evidence.length ? "ok" : "missing" });
        nodes.push({ id: "conclusion", kind: "conclusion", label: current.summary || (zh ? "研究结论" : "Research conclusion"), status: current.summary ? "ok" : "missing" });
        nodes.push({ id: "limitations", kind: "limitation", label: current.disclaimer || (zh ? "限制条件" : "Limitations"), status: current.disclaimer ? "ok" : "missing" });
        nodes.push({ id: "citations", kind: "citation", label: zh ? "引用/来源" : "Citations", count: current.citation_count ?? evidence.filter((item) => item.url).length });
        setEvidenceNodes(nodes);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [state.status, runId, run?.updated_at, zh]);

  useEffect(() => {
    if (state.status !== "available" || !runRef.current) return;
    let cancelled = false;
    getResearchRunArtifacts(runId)
      .then((payload) => {
        if (!cancelled) setArtifacts(payload.artifacts || []);
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [state.status, runId, run?.status]);

  return (
    <OceanShell locale={locale} variant="research" className="min-h-[calc(100dvh-7rem)] rounded-2xl">
      <div className="mx-auto max-w-5xl px-4 py-6 md:px-8">
        <CapabilityGate state={state} locale={locale} title={zh ? "Harness Research 暂不可用" : "Harness Research not available yet"} onRetry={retry}>
          {run ? (
            <div className="space-y-5">
              <header>
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <h1 className="text-xl font-semibold leading-tight md:text-2xl">{run.name || run.id}</h1>
                    <p className="mt-2 text-xs text-text-pg-dim">
                      {zh ? "创建" : "Created"} {formatTime(run.created_at, locale)} · {zh ? "更新" : "Updated"} {formatTime(run.updated_at, locale)} · {zh ? "耗时" : "Duration"} {formatDuration(run.created_at, run.updated_at, locale)}
                    </p>
                  </div>
                  <div className="flex flex-col items-end gap-1.5">
                    <StatusBadgeWithPulse domain="research" value={run.status} locale={locale} />
                    {ACTIVE_STATUSES.has(run.status) ? (
                      <span className="text-[10px] text-text-pg-dim">
                        {connectionMode === "sse" ? (zh ? "实时连接" : "Live connection") : (zh ? "连接恢复中 · 使用轮询更新" : "Reconnecting · polling updates")}
                      </span>
                    ) : null}
                  </div>
                </div>
                {run.is_degraded ? (
                  <p className="mt-3 border border-status-warning bg-bg-panel p-3 text-sm text-status-warning">
                    {zh ? "该任务结果已降级：部分证据缺失，结论仅供参考。" : "This run is degraded: some evidence is missing, conclusions are partial."}
                  </p>
                ) : null}
                {run.status === "failed" || run.status === "timed_out" ? (
                  <p className="mt-3 border border-status-negative bg-bg-panel p-3 text-sm text-status-negative">
                    {run.error_message || (zh ? "任务失败，请查看服务端状态。" : "Run failed; see the server-side status.")}
                  </p>
                ) : null}
              </header>

              <section className="border border-border-pg bg-bg-panel p-4 md:p-5">
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-text-pg-muted">{zh ? "任务时间线" : "Run timeline"}</h2>
                <ResearchTimeline locale={locale} nodes={stagesForStatus(run.status)} />
              </section>

              <section className="border border-border-pg bg-bg-panel p-4 md:p-5">
                <h2 className="mb-4 text-sm font-semibold uppercase tracking-wide text-text-pg-muted">{zh ? "证据关系" : "Evidence relationships"}</h2>
                {evidenceNodes.length ? <EvidenceGraph nodes={evidenceNodes} locale={locale} /> : <p className="text-sm text-text-pg-muted">{zh ? "证据数据将在任务完成后显示。" : "Evidence will appear once the run produces it."}</p>}
              </section>

              <section className="border border-border-pg bg-bg-panel p-4 md:p-5">
                <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-text-pg-muted">{zh ? "研究产出" : "Research artifact"}</h2>
                {run.summary ? (
                  <>
                    <p className="whitespace-pre-wrap text-sm leading-6 text-text-pg">{run.summary}</p>
                    {artifacts.length ? (
                      <ul className="mt-4 space-y-2 border-t border-border-pg pt-3">
                        {artifacts.map((artifact) => (
                          <li key={artifact.id} className="flex items-center gap-2 text-xs">
                            <span className="border border-border-pg px-1.5 py-0.5 uppercase text-text-pg-muted">{artifact.type}</span>
                            {artifact.url ? (
                              <a href={artifact.url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-ocean-cyan hover:underline">
                                <LinkIcon className="h-3 w-3" aria-hidden />
                                {artifact.title}
                              </a>
                            ) : (
                              <span className="text-text-pg-muted">{artifact.title}</span>
                            )}
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </>
                ) : (
                  <p className="text-sm text-text-pg-muted">{zh ? "研究结果尚未生成。" : "The research artifact has not been produced yet."}</p>
                )}
                <div className="mt-4 border-t border-border-pg pt-3">
                  <p className="text-xs leading-5 text-text-pg-muted">{run.disclaimer || (zh ? "研究结论未经人工验证，不构成事实断言或投资建议。任何自动交易建议仅作为研究结果 / 策略草案展示，不会直接执行。" : "Conclusions are not human-verified and are not factual assertions or investment advice. Any automated trading suggestion is shown strictly as research output / strategy draft and is never executed directly.")}</p>
                </div>
              </section>

              <p className="text-xs text-text-pg-dim">
                <a href={withLocale(locale, "/research")} className="inline-flex items-center gap-1 hover:text-text-pg-muted">← {zh ? "返回研究任务列表" : "Back to research runs"}</a>
              </p>
            </div>
          ) : null}
        </CapabilityGate>
      </div>
    </OceanShell>
  );
}
