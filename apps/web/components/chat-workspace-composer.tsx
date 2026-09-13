"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Paperclip, ArrowUp, Square, X, FileText, Loader2, RotateCcw, ShieldCheck } from "lucide-react";
import { apiBaseUrl, uploadAgentAttachment, getChatWorkspaceCapabilities, type AgentAttachment, type AgentPermissionMode } from "@/lib/api";
import type { Locale } from "@/i18n/routing";

const copy = {
  zh: { add: "添加文件", remove: "移除", retry: "重试", uploading: "上传中", failed: "上传失败", send: "发送", stop: "停止生成", placeholder: "向 PureGamma 提问…", permission: "对话权限", read: "仅可查看", ask: "修改前确认", full: "自动执行", confirm: "启用自动执行？Agent 可直接执行你账户内允许的工具操作。套餐限制、交易确认和风控仍然生效，不提供服务器文件或命令访问。", scope: "权限仅适用于你自己的 PureGamma 数据与工具。", drop: "松开以添加附件", unavailable: "附件服务暂不可用", limit: "文件数量或大小超限", unsupported: "不支持此文件格式", error: "请检查文件格式、大小或存储额度后重试。", preview: "预览图片", close: "关闭预览", files: "附件", select: "请选择文件", details: "研究设置", research: "研究", online: "联网", imageNote: "图片仅支持 DeepSeek V4.1 Flash。", fileOnly: "请分析所附文件。" },
  en: { add: "Add files", remove: "Remove", retry: "Retry", uploading: "Uploading", failed: "Upload failed", send: "Send", stop: "Stop generation", placeholder: "Ask PureGamma…", permission: "Conversation permissions", read: "Read only", ask: "Ask before changes", full: "Auto execute", confirm: "Enable automatic execution? The agent may run tools allowed for your account. Plan limits, trading confirmations and risk checks still apply. This does not grant server filesystem or shell access.", scope: "Permissions apply only to your PureGamma data and tools.", drop: "Drop to attach", unavailable: "Attachments are temporarily unavailable", limit: "File count or size limit exceeded", unsupported: "Unsupported file format", error: "Check the file format, size or storage allowance, then retry.", preview: "Preview image", close: "Close preview", files: "Attachments", select: "Choose files", details: "Research settings", research: "Research", online: "Web", imageNote: "Images require DeepSeek V4.1 Flash.", fileOnly: "Please analyze the attached files." }
};

export function AttachmentCards({ files, locale, onRemove }: { files: AgentAttachment[]; locale: Locale; onRemove?: (index: number) => void }) {
  const t = copy[locale === "zh" ? "zh" : "en"];
  const [preview, setPreview] = useState<AgentAttachment | null>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { if (preview) dialog.current?.showModal(); }, [preview]);
  const url = (file: AgentAttachment) => file.url ? `${apiBaseUrl()}${file.url}` : "";
  return <>
    <div className="flex max-w-full gap-2 overflow-x-auto py-2" aria-label={t.files}>
      {files.map((file, index) => <div key={file.id || `${file.name}-${index}`} className="relative flex h-16 w-56 shrink-0 items-center gap-3 rounded-lg bg-[var(--pg-surface-2)] px-3 text-sm">
        {file.kind === "image" && file.url ? <button type="button" onClick={() => setPreview(file)} aria-label={`${t.preview}: ${file.name}`} className="shrink-0 rounded-md focus-visible:ring-2">
          {/* Authenticated immutable image endpoint; never a public storage URL. */}
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={url(file)} alt={file.name} className="h-12 w-12 rounded-md object-cover" />
        </button> : <FileText className="h-6 w-6 shrink-0 text-text-pg-muted" />}
        <div className="min-w-0 flex-1">
          {file.url ? <a href={url(file)} target="_blank" rel="noreferrer" className="block truncate underline-offset-2 hover:underline" title={file.name}>{file.name}</a> : <span className="block truncate" title={file.name}>{file.name}</span>}
          <span className="text-xs text-text-pg-muted">{file.name.split(".").pop()?.toUpperCase()} · {Math.ceil((file.size ?? new TextEncoder().encode(file.content).length) / 1024)} KB</span>
        </div>
        {onRemove ? <button type="button" onClick={() => onRemove(index)} aria-label={`${t.remove}: ${file.name}`} className="grid h-9 w-8 shrink-0 place-items-center rounded-md hover:bg-[var(--pg-surface-hover)]"><X className="h-4 w-4" /></button> : null}
      </div>)}
    </div>
    <dialog ref={dialog} onClose={() => setPreview(null)} onClick={event => { if (event.target === dialog.current) dialog.current.close(); }} className="max-h-[90dvh] max-w-[92vw] rounded-xl bg-[var(--pg-surface-1)] p-4 text-text-pg backdrop:bg-black/60">
      <button type="button" autoFocus onClick={() => dialog.current?.close()} className="mb-3 flex min-h-10 items-center gap-2" aria-label={t.close}><X className="h-5 w-5" />{t.close}</button>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      {preview ? <img src={url(preview)} alt={preview.name} className="max-h-[72dvh] max-w-full object-contain" /> : null}
    </dialog>
  </>;
}

type Props = {
  locale: Locale; input: string; onInput: (value: string) => void;
  busy: boolean; onSend: () => void; onStop: () => void;
  attachments: AgentAttachment[]; onAttachments: (files: AgentAttachment[]) => void;
  permission: AgentPermissionMode; onPermission: (value: AgentPermissionMode, acknowledged: boolean) => Promise<void>;
  modelControl: ReactNode; researchMode: boolean; onResearch: (value: boolean) => void; settings: ReactNode;
  onUploading: (value: boolean) => void;
  /** Lets the parent put the caret back in the message box (e.g. after a starter prompt). */
  onTextarea?: (node: HTMLTextAreaElement | null) => void;
};

export function ChatWorkspaceComposer(p: Props) {
  const t = copy[p.locale === "zh" ? "zh" : "en"];
  const input = useRef<HTMLInputElement>(null);
  const textarea = useRef<HTMLTextAreaElement | null>(null);
  const filesRef = useRef(p.attachments);
  filesRef.current = p.attachments;
  const uploadLock = useRef(false);
  const [uploading, setUploading] = useState<string | null>(null);
  const [failed, setFailed] = useState<File[]>([]);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [changing, setChanging] = useState(false);
  const [limits, setLimits] = useState<{max_file_bytes: number; max_files: number; file_types: string[]} | null>(null);
  useEffect(() => { let active = true; getChatWorkspaceCapabilities().then(value => { if (active) setLimits(value); }).catch(() => { if (active) setError(t.unavailable); }); return () => { active = false; }; }, [t.unavailable]);
  useEffect(() => { if (textarea.current) { textarea.current.style.height = "auto"; textarea.current.style.height = `${Math.min(textarea.current.scrollHeight, 200)}px`; } }, [p.input]);

  async function add(files: File[]) {
    if (p.busy || uploadLock.current || !limits) return;
    setError("");
    if (filesRef.current.length + files.length > limits.max_files) { setError(t.limit); return; }
    uploadLock.current = true; p.onUploading(true);
    try {
      for (const file of files) {
        if (file.size > limits.max_file_bytes) { setError(`${file.name}: ${t.limit}`); continue; }
        if (!limits.file_types.includes(file.name.split(".").pop()?.toLowerCase() || "")) { setError(`${file.name}: ${t.unsupported}`); continue; }
        setUploading(file.name);
        try {
          const result = await uploadAgentAttachment(file);
          const next = [...filesRef.current, result.attachment];
          filesRef.current = next; p.onAttachments(next);
          setFailed(current => current.filter(item => item !== file));
        } catch { setFailed(current => current.includes(file) ? current : [...current, file]); setError(t.error); }
      }
    } finally { setUploading(null); uploadLock.current = false; p.onUploading(false); if (input.current) input.current.value = ""; }
  }

  async function changePermission(mode: AgentPermissionMode) {
    if (mode === "full-access" && !window.confirm(t.confirm)) return;
    setChanging(true);
    try { await p.onPermission(mode, mode === "full-access"); } catch { setError(t.unavailable); }
    finally { setChanging(false); }
  }

  return <div className="relative mx-auto w-full max-w-3xl" data-testid="harness-composer"
    onDragOver={event => { if (event.dataTransfer.types.includes("Files")) { event.preventDefault(); setDragging(true); } }}
    onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget as Node)) setDragging(false); }}
    onDrop={event => { event.preventDefault(); setDragging(false); void add(Array.from(event.dataTransfer.files)); }}>
    {dragging ? <div className="pointer-events-none absolute inset-0 z-20 grid place-items-center rounded-xl border-2 border-dashed border-[var(--pg-border-focus)] bg-[var(--pg-surface-1)] text-text-pg">{t.drop}</div> : null}
    {p.attachments.length ? <AttachmentCards files={p.attachments} locale={p.locale} onRemove={p.busy || uploading ? undefined : index => p.onAttachments(p.attachments.filter((_, i) => i !== index))} /> : null}
    {uploading ? <div className="flex items-center gap-2 py-2 text-sm" role="status"><Loader2 className="h-4 w-4 animate-spin" />{t.uploading} · {uploading}</div> : null}
    {failed.map((file, index) => <div key={`${file.name}-${index}`} className="flex items-center gap-2 py-1 text-sm text-status-negative"><span className="min-w-0 flex-1 truncate">{t.failed}: {file.name}</span><button disabled={!!uploading || p.busy} type="button" className="p-2" onClick={() => void add([file])} aria-label={`${t.retry}: ${file.name}`}><RotateCcw className="h-4 w-4" /></button><button type="button" className="p-2" onClick={() => setFailed(current => current.filter(item => item !== file))} aria-label={`${t.remove}: ${file.name}`}><X className="h-4 w-4" /></button></div>)}
    <form onSubmit={event => { event.preventDefault(); if (!uploadLock.current && !changing && !failed.length) p.onSend(); }} className="rounded-xl bg-[var(--pg-surface-raised)] p-3 shadow-sm focus-within:ring-2 focus-within:ring-[var(--pg-focus-ring)]">
      <textarea ref={node => { textarea.current = node; p.onTextarea?.(node); }} value={p.input} onChange={event => p.onInput(event.target.value)} rows={2} aria-label={t.placeholder} placeholder={t.placeholder} data-testid="chat-composer-input"
        onPaste={event => { if (event.clipboardData.files.length) { event.preventDefault(); void add(Array.from(event.clipboardData.files)); } }}
        onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); if (!uploadLock.current && !changing && !failed.length) p.onSend(); } }}
        className="block min-h-16 w-full resize-none bg-transparent px-1 py-2 text-base leading-6 text-text-pg outline-none" />
      <div className="flex flex-wrap items-center gap-1.5">
        <input ref={input} type="file" multiple accept={limits?.file_types.map(ext => `.${ext}`).join(",")} className="hidden" onChange={event => void add(Array.from(event.target.files || []))} />
        <button type="button" disabled={p.busy || !!uploading || !limits} onClick={() => input.current?.click()} aria-label={t.add} title={limits ? `${limits.max_files} files · ${limits.max_file_bytes / 1048576} MB/file` : t.unavailable} className="grid h-10 w-10 shrink-0 place-items-center rounded-lg hover:bg-[var(--pg-surface-hover)] disabled:opacity-40"><Paperclip className="h-5 w-5" /></button>
        <div className="min-w-0 max-w-full">{p.modelControl}</div>
        <label className="flex min-w-0 items-center gap-1 text-xs text-text-pg-muted" title={t.scope}><ShieldCheck className="h-4 w-4 shrink-0" /><span className="sr-only">{t.permission}</span><select aria-label={t.permission} disabled={p.busy || changing} value={p.permission} onChange={event => void changePermission(event.target.value as AgentPermissionMode)} className="min-h-10 max-w-full rounded-md bg-transparent text-text-pg focus-visible:ring-2"><option value="read-only">{t.read}</option><option value="workspace-write">{t.ask}</option><option value="full-access">{t.full}</option></select></label>
        <button type="button" disabled={p.busy} onClick={() => p.onResearch(!p.researchMode)} aria-pressed={p.researchMode} className="min-h-10 rounded-md px-2 text-xs text-text-pg-muted hover:bg-[var(--pg-surface-hover)]">{p.researchMode ? t.research : t.online}</button>
        <div className="ml-auto">{p.busy ? <button type="button" onClick={p.onStop} aria-label={t.stop} className="grid h-11 w-11 place-items-center rounded-lg text-status-negative"><Square className="h-5 w-5" /></button> : <button type="submit" disabled={(!p.input.trim() && !p.attachments.length) || !!uploading || changing || !!failed.length} aria-label={t.send} className="grid h-11 w-11 place-items-center rounded-lg bg-[var(--pg-surface-inverse)] text-[var(--pg-text-inverse)] disabled:opacity-40"><ArrowUp className="h-5 w-5" /></button>}</div>
      </div>
    </form>
    {error ? <p role="alert" className="mt-2 text-sm text-status-negative">{error} <button onClick={() => setError("")} aria-label={t.remove} type="button" className="p-1">×</button></p> : null}
    {p.researchMode ? <details className="mt-2 text-sm text-text-pg-muted"><summary className="cursor-pointer py-1">{t.details}</summary><div className="max-h-[40dvh] overflow-y-auto py-3">{p.settings}</div></details> : null}
  </div>;
}
