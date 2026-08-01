"use client";

import { useState } from "react";
import { Loader2, Save, Send } from "lucide-react";
import { Badge, ResearchCard, StatusDot } from "@/components/puregamma";
import type { Locale } from "@/i18n/routing";
import { confirmIMessageVerification, DailyPushPreference, DeliveryRecord, requestIMessageVerification, sendDailyPushTest, updateDailyPushPreferences } from "@/lib/api";

const CONTENT_FIELDS = ["include_portfolio", "include_market", "include_signals", "include_risk", "include_sentiment"] as const;

export function DailyPushSettings({ initial, initialHistory, locale, plan }: { initial: DailyPushPreference; initialHistory: DeliveryRecord[]; locale: Locale; plan: string }) {
  const zh = locale === "zh";
  const [value, setValue] = useState(initial);
  const [history, setHistory] = useState(initialHistory);
  const [busy, setBusy] = useState<"save" | "test" | "">("");
  const [message, setMessage] = useState("");
  const [challenge, setChallenge] = useState("");
  const [code, setCode] = useState("");
  const channels = plan === "Max" || plan === "Enterprise" ? ["email", "telegram", "imessage"] : plan === "Pro" ? ["email", "telegram"] : ["email"];
  const set = <K extends keyof DailyPushPreference>(key: K, next: DailyPushPreference[K]) => setValue((current) => ({ ...current, [key]: next }));
  const save = async () => {
    setBusy("save"); setMessage("");
    try { setValue((await updateDailyPushPreferences(value)).preference); setMessage(zh ? "设置已保存" : "Settings saved"); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(""); }
  };
  const test = async () => {
    setBusy("test"); setMessage("");
    try { const result = await sendDailyPushTest(value.channel, locale); setHistory((items) => [result.delivery, ...items]); setMessage(zh ? "测试请求已记录" : "Test delivery recorded"); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(""); }
  };
  const requestCode = async () => {
    setBusy("test"); setMessage("");
    try { const result = await requestIMessageVerification(value.recipient || ""); setChallenge(result.challenge_id); if (result.development_code) setCode(result.development_code); set("recipient", result.recipient); setMessage(zh ? "验证码已发送" : "Verification code sent"); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(""); }
  };
  const confirmCode = async () => {
    setBusy("test"); setMessage("");
    try { const result = await confirmIMessageVerification(challenge, code); set("recipient_verified_at", result.recipient_verified_at); setMessage(zh ? "号码已验证" : "Recipient verified"); }
    catch (error) { setMessage((error as Error).message); }
    finally { setBusy(""); }
  };
  return <div className="space-y-4">
    <ResearchCard>
      <div className="mb-4 flex items-center justify-between"><h2 className="font-semibold">{zh ? "投递设置" : "Delivery settings"}</h2><label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={value.enabled} onChange={(event) => set("enabled", event.target.checked)} />{zh ? "启用" : "Enabled"}</label></div>
      <div className="grid gap-4 md:grid-cols-3">
        <Field label={zh ? "渠道" : "Channel"}><select value={value.channel} onChange={(event) => set("channel", event.target.value as DailyPushPreference["channel"])} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm">{channels.map((channel) => <option key={channel}>{channel}</option>)}</select></Field>
        <Field label={zh ? "时区" : "Timezone"}><input value={value.timezone} onChange={(event) => set("timezone", event.target.value)} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" placeholder="Asia/Shanghai" /></Field>
        <Field label={zh ? "本地时间" : "Local time"}><input type="time" value={value.local_time} onChange={(event) => set("local_time", event.target.value)} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" /></Field>
      </div>
      <div className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-5">{CONTENT_FIELDS.map((key) => <label key={key} className="flex items-center gap-2 border border-border-pg p-3 text-sm"><input type="checkbox" checked={value[key]} onChange={(event) => set(key, event.target.checked)} />{key.replace("include_", "").replace("_", " ")}</label>)}</div>
      {value.channel === "imessage" ? <div className="mt-4 grid gap-3 border border-border-pg p-4 md:grid-cols-[1fr_auto_140px_auto]"><input value={value.recipient || ""} onChange={(event) => set("recipient", event.target.value)} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" placeholder="+15555550100" /><button type="button" onClick={requestCode} disabled={Boolean(busy)} className="border border-border-pg px-3 py-2 text-sm">{zh ? "发送验证码" : "Send code"}</button><input value={code} onChange={(event) => setCode(event.target.value)} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm" inputMode="numeric" maxLength={6} placeholder="000000" /><button type="button" onClick={confirmCode} disabled={Boolean(busy) || !challenge} className="border border-border-pg px-3 py-2 text-sm">{zh ? "确认" : "Verify"}</button><p className="text-xs text-text-pg-muted md:col-span-4">{value.recipient_verified_at ? (zh ? "已验证" : "Verified") : (zh ? "尚未验证" : "Not verified")}</p></div> : null}
      <div className="mt-4 flex flex-wrap items-center gap-3"><button type="button" onClick={save} disabled={Boolean(busy)} className="inline-flex items-center gap-2 border border-border-pg px-4 py-2 text-sm"><Save className="h-4 w-4" />{zh ? "保存" : "Save"}</button><button type="button" onClick={test} disabled={Boolean(busy)} className="inline-flex items-center gap-2 border border-border-pg px-4 py-2 text-sm"><Send className="h-4 w-4" />{zh ? "测试发送" : "Send test"}</button>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}<span className="text-sm text-text-pg-muted">{message}</span></div>
      <p className="mt-4 text-xs text-text-pg-muted">{zh ? "下次投递" : "Next delivery"}: {value.next_delivery_at ? new Date(value.next_delivery_at).toLocaleString(locale) : "-"}</p>
    </ResearchCard>
    <ResearchCard><h2 className="mb-3 font-semibold">{zh ? "投递记录" : "Delivery ledger"}</h2><div className="space-y-2">{history.map((item) => <div key={item.id} className="grid gap-2 border border-border-pg p-3 text-sm md:grid-cols-4"><span>{new Date(item.created_at).toLocaleString(locale)}</span><span>{item.channel}</span><Badge tone="neutral"><StatusDot tone={item.status === "sent" ? "emerald" : "amber"} />{item.status}</Badge><span className="text-status-warning">{item.provider_response?.reason || "-"}</span></div>)}{!history.length ? <p className="text-sm text-text-pg-muted">{zh ? "暂无投递记录" : "No deliveries yet"}</p> : null}</div></ResearchCard>
  </div>;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) { return <label className="text-sm"><span className="mb-1 block text-text-pg-muted">{label}</span>{children}</label>; }
