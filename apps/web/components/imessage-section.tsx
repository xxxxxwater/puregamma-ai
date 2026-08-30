"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { MessageCircle, Send, ShieldCheck, Smartphone } from "lucide-react";
import {
  confirmIMessageVerification,
  getIMessageConfig,
  requestIMessageVerification,
  sendIMessageTest,
  type IMessageConfig
} from "@/lib/api";

export type IMessageCopy = {
  title: string;
  subtitle: string;
  officialNumber: string;
  bound: string;
  verifiedAt: string;
  notBound: string;
  recipientPlaceholder: string;
  sendCode: string;
  sending: string;
  codePlaceholder: string;
  confirm: string;
  planRequired: string;
  test: string;
  testing: string;
  testSent: string;
  error: string;
};

function fmt(value: string | null, fallback: string): string {
  if (!value) return fallback;
  try { return new Date(value).toLocaleString(); } catch { return value; }
}

export function IMessageSection({ copy }: { copy: IMessageCopy }) {
  const [config, setConfig] = useState<IMessageConfig | null>(null);
  const [recipient, setRecipient] = useState("");
  const [code, setCode] = useState("");
  const [challenge, setChallenge] = useState<{ id: string; expires_at: string; development_code?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");

  const load = useCallback(async () => {
    try { setConfig(await getIMessageConfig()); } catch { setConfig(null); }
  }, []);

  useEffect(() => { void load(); }, [load]);

  function interpolate(template: string, values: Record<string, string>) {
    return Object.entries(values).reduce((out, [k, v]) => out.replaceAll(`{${k}}`, v), template);
  }

  async function sendCode(event: FormEvent) {
    event.preventDefault();
    if (!recipient.trim()) return;
    setBusy(true);
    setNote("");
    try {
      const result = await requestIMessageVerification(recipient.trim());
      setChallenge({ id: result.challenge_id, expires_at: result.expires_at, development_code: result.development_code });
      if (result.development_code) setNote(result.development_code);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "";
      setNote(/403|plan/i.test(message) ? copy.planRequired : copy.error);
    } finally { setBusy(false); }
  }

  async function confirm(event: FormEvent) {
    event.preventDefault();
    if (!challenge || !code.trim()) return;
    setBusy(true);
    setNote("");
    try {
      await confirmIMessageVerification(challenge.id, code.trim());
      setChallenge(null);
      setCode("");
      await load();
    } catch { setNote(copy.error); } finally { setBusy(false); }
  }

  async function sendTest() {
    setBusy(true);
    setNote("");
    try {
      await sendIMessageTest();
      setNote(copy.testSent);
    } catch (exc) {
      const message = exc instanceof Error ? exc.message : "";
      setNote(/403|plan/i.test(message) ? copy.planRequired : copy.error);
    } finally { setBusy(false); }
  }

  if (!config) {
    return <section className="rounded-2xl border border-border-pg bg-bg-panel p-5 text-sm text-text-pg-muted">{copy.error}</section>;
  }

  return (
    <section className="rounded-2xl border border-border-pg bg-bg-panel p-5">
      <div className="flex items-center gap-2 text-sm font-semibold"><MessageCircle className="h-4 w-4 text-status-positive" />{copy.title}</div>
      <p className="mt-2 text-sm leading-6 text-text-pg-muted">{copy.subtitle}</p>

      <div className="mt-4 space-y-4">
        <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border-pg bg-bg-app px-4 py-3">
          <span className="text-xs uppercase tracking-[0.14em] text-text-pg-dim">{copy.officialNumber}</span>
          <span className="font-mono text-sm text-text-pg">{config.official_number}</span>
        </div>

        {config.recipient && config.recipient_verified_at ? (
          <div className="space-y-3">
            <div className="flex flex-wrap items-center gap-2 text-sm text-text-pg">
              <ShieldCheck className="h-4 w-4 text-status-positive" />
              {interpolate(copy.bound, { recipient: config.recipient })}
              <span className="text-xs text-text-pg-muted">{interpolate(copy.verifiedAt, { time: fmt(config.recipient_verified_at, "") })}</span>
            </div>
            <button type="button" disabled={busy} onClick={() => void sendTest()} className="inline-flex items-center gap-2 rounded-lg border border-border-pg px-3 py-2 text-xs font-medium text-text-pg-muted hover:border-border-pg-strong hover:text-text-pg disabled:opacity-50">
              <Send className="h-3.5 w-3.5" />{busy ? copy.testing : copy.test}
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center gap-2 text-sm text-text-pg-muted"><Smartphone className="h-4 w-4" />{copy.notBound}</div>
            {!challenge ? (
              <form onSubmit={sendCode} className="flex flex-wrap items-center gap-2">
                <input value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder={copy.recipientPlaceholder} inputMode="tel" className="h-9 min-w-0 flex-1 rounded-lg border border-border-pg bg-bg-app px-3 text-sm outline-none focus:border-border-pg-strong sm:w-64" />
                <button type="submit" disabled={busy} className="h-9 rounded-lg border border-border-pg-strong bg-pg-white px-3 text-xs font-semibold text-pg-black disabled:opacity-50">{busy ? copy.sending : copy.sendCode}</button>
              </form>
            ) : (
              <form onSubmit={confirm} className="flex flex-wrap items-center gap-2">
                <input value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} placeholder={copy.codePlaceholder} className="h-9 w-40 rounded-lg border border-border-pg bg-bg-app px-3 text-sm tracking-[0.25em] outline-none focus:border-border-pg-strong" />
                <button type="submit" disabled={busy} className="h-9 rounded-lg border border-border-pg-strong bg-pg-white px-3 text-xs font-semibold text-pg-black disabled:opacity-50">{copy.confirm}</button>
              </form>
            )}
          </div>
        )}
        {note ? <div className="text-xs text-text-pg-muted">{note}</div> : null}
      </div>
    </section>
  );
}
