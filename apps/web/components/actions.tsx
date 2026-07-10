"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { CreditCard, ExternalLink, Play, Send } from "lucide-react";
import { API_URL, cancelSubscription, createBillingCheckout, createPortalSession, reactivateSubscription, sendReport } from "@/lib/api";
import { Button } from "@/components/ui";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { t } from "@/lib/translations";

async function post(path: string, body: unknown) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export function BillingButton({
  plan,
  checkoutMode = "session",
  disabled = false,
  disabledMessage
}: {
  plan: "Pro" | "Max" | "Enterprise";
  checkoutMode?: "session" | "payment_link";
  disabled?: boolean;
  disabledMessage?: string;
}) {
  const [busy, setBusy] = useState(false);
  const locale = useLocale();
  return (
    <div className="space-y-2">
      <Button
        disabled={busy || disabled}
        onClick={async () => {
          setBusy(true);
          try {
            const data = await createBillingCheckout(plan, checkoutMode, locale);
            window.location.href = data.checkout_url;
          } finally {
            setBusy(false);
          }
        }}
      >
        <CreditCard className="h-4 w-4" aria-hidden />
        {t(locale, "common.actions.upgradeTo", { plan })}
      </Button>
      {disabled && disabledMessage ? <p className="text-xs text-status-warning">{disabledMessage}</p> : null}
    </div>
  );
}

export function PortalButton() {
  const [busy, setBusy] = useState(false);
  const locale = useLocale();
  return (
    <Button
      variant="secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          const data = await createPortalSession(locale);
          window.location.href = data.portal_url;
        } finally {
          setBusy(false);
        }
      }}
    >
      <ExternalLink className="h-4 w-4" aria-hidden />
      {t(locale, "common.actions.manageSubscription")}
    </Button>
  );
}

export function SubscriptionLifecycleButton({ mode }: { mode: "cancel" | "reactivate" }) {
  const [busy, setBusy] = useState(false);
  const locale = useLocale();
  const router = useRouter();
  return (
    <Button
      variant="secondary"
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          if (mode === "cancel") {
            await cancelSubscription(locale);
          } else {
            await reactivateSubscription(locale);
          }
          router.refresh();
        } finally {
          setBusy(false);
        }
      }}
    >
      {mode === "cancel" ? t(locale, "billing.cancelSubscription") : t(locale, "billing.reactivateSubscription")}
    </Button>
  );
}

export function SendReportButton({ channel, reportId }: { channel: string; reportId: string }) {
  const [status, setStatus] = useState("");
  const locale = useLocale();
  return (
    <Button
      variant="secondary"
      onClick={async () => {
        setStatus("sending");
        const data = await sendReport(channel, locale);
        setStatus(data.delivery.status);
      }}
    >
      <Send className="h-4 w-4" aria-hidden />
      {channel}
      {status ? <span className="text-xs text-neutral-500">{status}</span> : null}
    </Button>
  );
}

export function GeneratePlaybookButton() {
  const [status, setStatus] = useState("");
  const locale = useLocale();
  return (
    <Button
      onClick={async () => {
        setStatus("running");
        try {
          await post("/playbooks/generate", {});
          setStatus("done");
        } catch {
          setStatus("blocked");
        }
      }}
    >
      <Play className="h-4 w-4" aria-hidden />
      {t(locale, "common.actions.generatePlaybook")}
      {status ? <span className="text-xs opacity-80">{status}</span> : null}
    </Button>
  );
}
