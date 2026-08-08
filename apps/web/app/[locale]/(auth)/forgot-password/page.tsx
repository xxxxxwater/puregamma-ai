"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Loader2 } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { forgotPassword } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";



export default function ForgotPasswordPage() {
  const locale = useLocale();
  const zh = locale === "zh";
  const [busy, setBusy] = useState(false);
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [failed, setFailed] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
    setBusy(true);
    setFailed(false);
    try {
      await forgotPassword(email);
      setSent(true);
    } catch {
      setFailed(true);
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <div className="space-y-6">
        <div className="space-y-6 text-center">
          <h1 className="text-2xl font-semibold">{t(locale, "common.auth.forgotPasswordTitle")}</h1>
          <p className="text-sm text-text-pg-muted">{t(locale, "common.auth.resetLinkSent")}</p>
          <Link href={withLocale(locale, "/login")} className="inline-block text-sm font-medium text-text-pg underline underline-offset-2">
            {t(locale, "common.auth.signInLink")}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="space-y-6">
        <div className="text-center">
          <Link href={withLocale(locale, "/")} className="inline-flex items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={32} height={32} className="mx-auto" />
            PureGamma AI
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{t(locale, "common.auth.forgotPasswordTitle")}</h1>
          <p className="mt-2 text-sm text-text-pg-muted">{t(locale, "common.auth.forgotPasswordDescription")}</p>
        </div>

        <div className="space-y-4 border border-border-pg bg-bg-panel p-6 rounded-2xl">
          {failed ? <p className="border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm text-status-negative rounded-lg">{zh ? "发送失败，请稍后重试" : "Failed to send the reset link. Please try again later."}</p> : null}
          <form onSubmit={handleSubmit} className="space-y-3">
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t(locale, "common.auth.emailPlaceholder")} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong rounded-lg" required />
            <button type="submit" disabled={busy || !email} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-pg-white px-4 py-2.5 text-sm font-semibold text-pg-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 rounded-lg">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t(locale, "common.auth.sendResetLink")}
            </button>
          </form>
        </div>

        <p className="text-center text-sm text-text-pg-muted">
          <Link href={withLocale(locale, "/login")} className="font-medium text-text-pg underline underline-offset-2">
            {t(locale, "common.auth.signInLink")}
          </Link>
        </p>
      </div>
    </div>
  );
}
