"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Chrome, Loader2 } from "lucide-react";
import { AuthLegalNotice } from "@/components/auth-legal-notice";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { googleLogin, emailRegister } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export default function SignUpPage() {
  const locale = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const zh = locale === "zh";

  const handleGoogleLogin = async () => {
    setBusy(true);
    setError("");
    try {
      const result = await googleLogin(locale);
      window.location.href = result.auth_url;
    } catch {
      setError(t(locale, "common.auth.googleCallbackError"));
      setBusy(false);
    }
  };

  const handleEmailRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;
    setBusy(true);
    setError("");
    try {
      await emailRegister(email, password, name, locale);
      setSuccess(true);
    } catch (err: unknown) {
      const status = (err as { status?: number }).status;
      if (status === 409) setError(t(locale, "common.auth.emailAlreadyRegistered"));
      else if (status === 400) setError(t(locale, "common.auth.passwordTooShort"));
      else setError(zh ? "注册失败，请稍后重试" : "Registration failed. Please try again later.");
    } finally {
      setBusy(false);
    }
  };

  if (success) {
    return (
      <div className="flex min-h-[80vh] items-center justify-center">
        <div className="w-full max-w-md space-y-6 text-center">
          <h1 className="text-2xl font-semibold">{t(locale, "common.auth.verifyEmailTitle")}</h1>
          <p className="text-sm text-text-pg-muted">{t(locale, "common.auth.registerSuccess")}</p>
          <p className="text-xs text-text-pg-dim">{t(locale, "common.auth.checkSpamFolder")}</p>
          <div className="flex justify-center gap-4 text-sm">
            <Link href={withLocale(locale, "/verify-email")} className="font-medium text-text-pg underline underline-offset-2">{t(locale, "common.auth.resendVerification")}</Link>
            <Link href={withLocale(locale, "/login")} className="font-medium text-text-pg underline underline-offset-2">{t(locale, "common.auth.signInLink")}</Link>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <Link href={withLocale(locale, "/")} className="inline-flex items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={32} height={32} className="mx-auto" />
            PureGamma AI
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{t(locale, "common.auth.registerTitle")}</h1>
        </div>

        <div className="space-y-4 border border-border-pg bg-bg-panel p-6">
          {error ? <p className="border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm text-status-negative">{error}</p> : null}

          <form onSubmit={handleEmailRegister} className="space-y-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t(locale, "common.auth.namePlaceholder")}
              className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong"
            />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t(locale, "common.auth.emailPlaceholder")}
              className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong"
              required
            />
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder={t(locale, "common.auth.passwordPlaceholder")}
              className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong"
              required
              minLength={8}
            />
            <button
              type="submit"
              disabled={busy || !email || !password}
              className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-text-pg px-4 py-2.5 text-sm font-semibold text-bg-panel transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t(locale, "common.auth.emailRegister")}
            </button>
          </form>

          <div className="flex items-center gap-3">
            <div className="h-px flex-1 bg-border-pg" />
            <span className="text-xs text-text-pg-dim">{t(locale, "common.auth.orContinueWith")}</span>
            <div className="h-px flex-1 bg-border-pg" />
          </div>

          <button type="button" disabled={busy} onClick={handleGoogleLogin} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm font-semibold text-text-pg transition hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-50">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Chrome className="h-4 w-4" />}
            {t(locale, "common.auth.googleLogin")}
          </button>
        </div>

        <p className="text-center text-sm text-text-pg-muted">
          {t(locale, "common.auth.hasAccount")}{" "}
          <Link href={withLocale(locale, "/login")} className="font-medium text-text-pg underline underline-offset-2">
            {t(locale, "common.auth.signInLink")}
          </Link>
        </p>

        <AuthLegalNotice locale={locale} mode="signup" />
      </div>
    </div>
  );
}
