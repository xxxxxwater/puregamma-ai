"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight, Bell, Info, Mail, MessageCircle, type LucideIcon } from "lucide-react";
import { Badge } from "@/components/puregamma";
import { normalizeLocale, withLocale, type Locale } from "@/i18n/routing";
import { saveOnboarding } from "@/lib/api";
import { getMessageNamespace, t } from "@/lib/translations";

const channelIcons: Record<string, LucideIcon> = {
  email: Mail,
  telegram: MessageCircle,
  imessage: Bell
};

type InputType = "email" | "text" | "tel";

export default function LocalizedOnboardingChannelsPage({ params }: { params: { locale: string } }) {
  const locale = normalizeLocale(params.locale);
  const router = useRouter();
  const copy = getMessageNamespace(locale, "onboarding").channels;
  const [busy, setBusy] = useState(false);
  const [channels, setChannels] = useState<Record<string, boolean>>({ email: true });
  const [recipients, setRecipients] = useState<Record<string, string>>({});

  const toggle = (id: string) => {
    setChannels((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleComplete = async () => {
    setBusy(true);
    const assets = JSON.parse(localStorage.getItem("pg_onboarding_assets") || "[\"BTC\",\"ETH\",\"SOL\"]");
    const style = localStorage.getItem("pg_onboarding_style") || "risk-controlled";
    const activeChannels = Object.entries(channels).filter(([, enabled]) => enabled).map(([key]) => key);

    try {
      const result = await saveOnboarding({
        preferred_assets: assets,
        preferred_style: style,
        notification_channels: activeChannels,
        email_recipient: recipients.email || "",
        telegram_chat_id: recipients.telegram || "",
        imessage_recipient: recipients.imessage || "",
      });
      localStorage.setItem("pg_user", JSON.stringify(result.user));
      localStorage.setItem("pg_onboarding_done", "true");
      localStorage.setItem("pg_onboarding_assets", JSON.stringify(assets));
      localStorage.setItem("pg_onboarding_style", style);
      localStorage.setItem("pg_onboarding_channels", JSON.stringify(activeChannels));
      router.push(withLocale(locale, "/dashboard"));
    } catch {
      const returnTo = encodeURIComponent(withLocale(locale, "/onboarding/channels"));
      router.push(`${withLocale(locale, "/login")}?returnTo=${returnTo}`);
    } finally {
      setBusy(false);
    }
  };

  const selectedCount = Object.values(channels).filter(Boolean).length;

  return (
    <div className="mx-auto max-w-3xl py-8">
      <div className="mb-8">
        <div className="flex items-center gap-3 text-[0.68rem] font-semibold uppercase tracking-[0.18em] text-text-pg-muted">
          <span>{copy.step}</span>
          <span className="text-text-pg">{copy.kicker}</span>
        </div>
        <h1 className="mt-4 text-3xl font-semibold">{copy.title}</h1>
        <p className="mt-3 max-w-xl text-sm leading-6 text-text-pg-muted">{copy.subtitle}</p>
      </div>

      <div className="space-y-3">
        {copy.items.map((channel) => {
          const Icon = channelIcons[channel.id] ?? Mail;
          const active = Boolean(channels[channel.id]);
          const locked = channel.id === "imessage";
          return (
            <div
              key={channel.id}
              className={`border p-5 transition ${
                active ? "border-border-pg-strong bg-bg-panel-muted" : locked ? "border-border-pg bg-bg-panel opacity-60" : "border-border-pg bg-bg-panel"
              }`}
            >
              <div className="flex items-start gap-4">
                <button
                  onClick={() => !locked && toggle(channel.id)}
                  disabled={locked}
                  className={`mt-0.5 border p-2.5 transition ${active ? "border-border-pg-strong bg-bg-panel-muted" : "border-border-pg bg-bg-panel-muted"} ${locked ? "cursor-not-allowed" : "cursor-pointer"}`}
                  aria-label={channel.label}
                >
                  <Icon className={`h-5 w-5 ${active ? "text-text-pg" : locked ? "text-text-pg-dim" : "text-text-pg-muted"}`} aria-hidden />
                </button>
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold">{channel.label}</span>
                    {channel.planRequired ? <Badge tone="amber">{t(locale, "onboarding.channels.required", { plan: channel.planRequired })}</Badge> : <Badge tone="emerald">{copy.free}</Badge>}
                  </div>
                  <p className="mt-1.5 text-sm leading-5 text-text-pg-muted">{channel.description}</p>
                  {active ? (
                    <input
                      type={inputType(channel.type)}
                      placeholder={channel.placeholder}
                      value={recipients[channel.id] || ""}
                      onChange={(event) => setRecipients((prev) => ({ ...prev, [channel.id]: event.target.value }))}
                      className="mt-3 w-full max-w-xs border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim focus:border-border-pg-strong focus:outline-none"
                    />
                  ) : null}
                </div>
                <button
                  onClick={() => !locked && toggle(channel.id)}
                  disabled={locked}
                  className={`mt-1 flex h-5 w-5 shrink-0 items-center justify-center border transition ${active ? "border-border-pg-strong bg-pg-white" : "border-border-pg"} ${locked ? "cursor-not-allowed opacity-30" : ""}`}
                  aria-label={channel.label}
                >
                  {active ? <span className="text-xs text-pg-black">✓</span> : null}
                </button>
              </div>
              {locked ? <p className="mt-3 ml-[3.25rem] text-xs text-status-warning">{copy.locked}</p> : null}
            </div>
          );
        })}
      </div>

      <div className="mt-8 flex items-center justify-between gap-4 border border-border-pg bg-bg-panel-muted px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-text-pg-muted">
          <Info className="h-4 w-4 shrink-0" aria-hidden />
          {selectedLabel(locale, selectedCount)}
        </div>
        <button
          onClick={handleComplete}
          disabled={busy || selectedCount === 0}
          className="inline-flex items-center gap-2 border border-border-pg-strong bg-pg-white px-5 py-2.5 text-sm font-semibold text-pg-black transition hover:bg-pg-white-soft disabled:cursor-not-allowed disabled:opacity-40"
        >
          {busy ? copy.settingUp : copy.complete}
          {!busy ? <ArrowRight className="h-4 w-4" aria-hidden /> : null}
        </button>
      </div>

      <p className="mt-4 text-center text-xs text-text-pg-dim">{copy.footer}</p>
    </div>
  );
}

function inputType(value: string): InputType {
  if (value === "email" || value === "tel") return value;
  return "text";
}

function selectedLabel(locale: Locale, count: number): string {
  return t(locale, count === 1 ? "onboarding.channels.selectedSingular" : "onboarding.channels.selected", { count });
}
