"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Globe, QrCode, RefreshCw, ShieldCheck, Smartphone } from "lucide-react";
import {
  getMobileAccessQr,
  getMobileAccessStatus,
  rotateMobileAccessPin,
  setMobileAccessPin,
  startMobileAccessTunnel,
  stopMobileAccessTunnel,
  type MobileAccessStatus
} from "@/lib/api";

export type RemoteCopy = {
  public: string;
  pin: string;
  show: string;
  hide: string;
  rotatePin: string;
  customPin: string;
  customPlaceholder: string;
  apply: string;
  startTunnel: string;
  stopTunnel: string;
  running: string;
  stopped: string;
  autoStart: string;
  restartNotice: string;
  userNote: string;
  loading: string;
  unavailable: string;
  notConfigured: string;
  retry: string;
};

function PinField({ value, copy, canManage, onRotate, onCustom }: {
  value: string;
  copy: RemoteCopy;
  canManage: boolean;
  onRotate: () => void;
  onCustom: (pin: string) => void;
}) {
  const [visible, setVisible] = useState(false);
  const [draft, setDraft] = useState("");
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-2xl tracking-[0.35em] text-text-pg">{visible ? value : "••••••••"}</span>
        <button type="button" onClick={() => setVisible((v) => !v)} className="rounded-md border border-border-pg px-2 py-1 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg">{visible ? copy.hide : copy.show}</button>
        {canManage ? <button type="button" onClick={onRotate} className="rounded-md border border-border-pg px-2 py-1 text-xs text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg"><RefreshCw className="mr-1 inline h-3 w-3" />{copy.rotatePin}</button> : null}
      </div>
      {canManage ? (
      <form onSubmit={(event) => { event.preventDefault(); if (draft.trim()) onCustom(draft.trim()); }} className="flex flex-wrap items-center gap-2">
        <label className="sr-only">{copy.customPin}</label>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} inputMode="numeric" pattern="[0-9]{8}" maxLength={8} placeholder={copy.customPlaceholder} className="h-9 w-40 rounded-lg border border-border-pg bg-bg-app px-3 text-sm tracking-[0.25em] outline-none focus:border-border-pg-strong" />
        <button type="submit" className="h-9 rounded-lg border border-border-pg-strong bg-pg-white px-3 text-xs font-semibold text-pg-black">{copy.apply}</button>
        <span className="text-xs text-text-pg-dim">{copy.customPin}</span>
      </form>
      ) : null}
    </div>
  );
}

export function MobileAccessPanel({ copy }: { copy: RemoteCopy }) {
  const [status, setStatus] = useState<MobileAccessStatus | null>(null);
  const [pubQr, setPubQr] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const isAdmin = status?.is_admin === true;

  const load = useCallback(async () => {
    try {
      const state = await getMobileAccessStatus();
      setStatus(state);
      setError("");
      if (state.public.running) setPubQr(await getMobileAccessQr("public"));
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : String(exc);
      setError(message.includes("503") || message.includes("not configured") ? copy.notConfigured : copy.unavailable);
    }
  }, [copy]);

  useEffect(() => { void load(); }, [load]);

  async function toggleTunnel() {
    if (!status) return;
    setBusy(true);
    try {
      if (status.public.running) await stopMobileAccessTunnel();
      else await startMobileAccessTunnel();
      await load();
    } finally { setBusy(false); }
  }

  async function rotate() {
    setBusy(true);
    try { await rotateMobileAccessPin("public"); await load(); } finally { setBusy(false); }
  }

  async function applyCustom(pin: string) {
    if (!/^\d{8}$/.test(pin)) return;
    setBusy(true);
    try { await setMobileAccessPin("public", pin); await load(); } finally { setBusy(false); }
  }

  if (!status && !error) {
    return <div className="rounded-xl border border-border-pg bg-bg-panel p-8 text-center text-sm text-text-pg-muted">{copy.loading}</div>;
  }

  return (
    <div className="space-y-4">
      {error ? (
        <div className="rounded-xl border border-status-negative/40 bg-bg-panel p-5">
          <strong className="text-sm">{error}</strong>
          <div className="mt-3"><button type="button" onClick={() => void load()} className="rounded-lg border border-border-pg px-3 py-2 text-sm">{copy.retry}</button></div>
        </div>
      ) : null}
      {status ? (
        <section className="rounded-2xl border border-border-pg bg-bg-panel p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-sm font-semibold"><Globe className="h-4 w-4 text-status-positive" />{copy.public}</div>
            <div className="flex items-center gap-3">
              <span className="text-xs text-text-pg-muted">{status.public.running ? copy.running : copy.stopped}</span>
              {isAdmin ? <button type="button" disabled={busy} onClick={() => void toggleTunnel()} className="rounded-lg border border-border-pg-strong bg-pg-white px-3 py-2 text-xs font-semibold text-pg-black disabled:opacity-50">{status.public.running ? copy.stopTunnel : copy.startTunnel}</button> : null}
            </div>
          </div>
          {status.public.running ? (
            <div className="mt-4 grid gap-4 md:grid-cols-[auto_1fr]">
              <div className="rounded-xl border border-border-pg bg-bg-app p-2"><img src={pubQr} alt="Public QR" className="h-44 w-44 rounded-lg" /></div>
              <div className="space-y-3">
                <div className="break-all font-mono text-xs text-text-pg-muted">{status.public.url}</div>
                <PinField value={status.public.pin} copy={copy} canManage={isAdmin} onRotate={() => void rotate()} onCustom={(pin) => void applyCustom(pin)} />
                {status.public.last_error ? <div className="text-xs text-status-negative">{status.public.last_error}</div> : null}
              </div>
            </div>
          ) : null}
          <div className="mt-3 flex items-center gap-2 text-xs text-text-pg-muted"><ShieldCheck className="h-3.5 w-3.5" />{status.public.auto_start ? copy.autoStart : copy.public}</div>
        </section>
      ) : null}
      {!isAdmin ? <div className="flex gap-2 rounded-xl border border-border-pg bg-bg-panel p-4 text-xs leading-5 text-text-pg-muted"><Smartphone className="mt-0.5 h-4 w-4 shrink-0" /><p>{copy.userNote}</p></div> : null}
      <div className="flex gap-2 rounded-xl border border-border-pg bg-bg-panel p-4 text-xs leading-5 text-text-pg-muted"><QrCode className="mt-0.5 h-4 w-4 shrink-0" /><p>{copy.restartNotice}</p></div>
    </div>
  );
}
