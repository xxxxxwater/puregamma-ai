"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Chrome, Loader2 } from "lucide-react";
import { AuthLegalNotice } from "@/components/auth-legal-notice";
import { WalletLoginButtons } from "@/components/wallet-login-buttons";
import { PasswordInput } from "@/components/password-input";
import { CaptchaModal } from "@/components/captcha-modal";
import type { CaptchaResult } from "@/components/puzzle-captcha";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { emailRegister, extractApiError, googleLogin } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";



const EMAIL_RE = /^[A-Za-z0-9._%+-]+@[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)+$/;

export default function SignUpPage() {
  const locale = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [captchaOpen, setCaptchaOpen] = useState(false);
  const [captchaError, setCaptchaError] = useState("");
  const [captchaKey, setCaptchaKey] = useState(0);
  const [captchaRetry, setCaptchaRetry] = useState(0);
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

  const openCaptcha = () => {
    setCaptchaError("");
    setCaptchaKey((key) => key + 1);
    setCaptchaOpen(true);
  };

  const handleEmailRegister = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password || busy) return;
    if (!EMAIL_RE.test(email.trim())) { setError(t(locale, "common.auth.invalidEmail")); return; }
    setError("");
    openCaptcha();
  };

  const handleCaptchaSolved = async (result: CaptchaResult) => {
    setBusy(true);
    setCaptchaError("");
    try {
      await emailRegister(email.trim(), password, name, locale, { captcha_id: result.captchaId, captcha_offset: result.offset });
      setCaptchaOpen(false);
      setSuccess(true);
    } catch (err: unknown) {
      const apiError = extractApiError(err);
      if (apiError.code === "CAPTCHA_FAILED") {
        // Same puzzle stays valid for a few attempts: just reset the slider.
        setCaptchaError(t(locale, "common.auth.captchaFailed"));
        setCaptchaRetry((key) => key + 1);
      } else if (apiError.code === "CAPTCHA_REQUIRED" || apiError.code === "CAPTCHA_EXPIRED" || apiError.code === "CAPTCHA_UNAVAILABLE") {
        setCaptchaError(t(locale, "common.auth.captchaExpired"));
        setCaptchaKey((key) => key + 1);
      } else {
        setCaptchaOpen(false);
        if (apiError.status === 409) setError(t(locale, "common.auth.emailAlreadyRegistered"));
        else if (apiError.code === "INVALID_EMAIL") setError(t(locale, "common.auth.invalidEmail"));
        else if (apiError.code === "PASSWORD_TOO_WEAK") setError(apiError.message || t(locale, "common.auth.passwordTooShort"));
        else if (apiError.status === 429) setError(zh ? "操作过于频繁，请稍后再试" : "Too many attempts. Please try again later.");
        else setError(zh ? "注册失败，请稍后重试" : "Registration failed. Please try again later.");
      }
    } finally {
      setBusy(false);
    }
  };

  if (success) {
    return (
      <div className="space-y-6">
        <div className="space-y-6 text-center">
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
    <div className="space-y-6">
      <div className="space-y-6">
        <div className="text-center">
          <Link href={withLocale(locale, "/")} className="inline-flex items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={32} height={32} className="mx-auto" />
            PureGamma AI
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{t(locale, "common.auth.registerTitle")}</h1>
        </div>

        <div className="space-y-4 border border-border-pg bg-bg-panel p-6 rounded-2xl">
          {error ? <p className="border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm text-status-negative rounded-lg">{error}</p> : null}

          <form onSubmit={handleEmailRegister} className="space-y-3">
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t(locale, "common.auth.namePlaceholder")}
              className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong rounded-lg"
            />
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder={t(locale, "common.auth.emailPlaceholder")}
              className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong rounded-lg"
              required
            />
            <PasswordInput
              value={password}
              onChange={setPassword}
              placeholder={t(locale, "common.auth.passwordPlaceholder")}
              minLength={8}
              autoComplete="new-password"
            />
            <button
              type="submit"
              disabled={busy || !email || !password}
              className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-pg-white px-4 py-2.5 text-sm font-semibold text-pg-black transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50 rounded-lg"
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

          <button type="button" disabled={busy} onClick={handleGoogleLogin} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm font-semibold text-text-pg transition hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-50 rounded-lg">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Chrome className="h-4 w-4" />}
            {t(locale, "common.auth.googleLogin")}
          </button>

          <WalletLoginButtons locale={locale} onError={setError} />
          <p className="text-center text-xs text-text-pg-dim">{t(locale, "common.auth.walletSignInHint")}</p>
        </div>

        <p className="text-center text-sm text-text-pg-muted">
          {t(locale, "common.auth.hasAccount")}{" "}
          <Link href={withLocale(locale, "/login")} className="font-medium text-text-pg underline underline-offset-2">
            {t(locale, "common.auth.signInLink")}
          </Link>
        </p>

        <AuthLegalNotice locale={locale} mode="signup" />
      </div>

      <CaptchaModal
        open={captchaOpen}
        busy={busy}
        error={captchaError}
        resetKey={captchaKey}
        retryToken={captchaRetry}
        onSolved={handleCaptchaSolved}
        onClose={() => setCaptchaOpen(false)}
        onRefresh={() => setCaptchaError("")}
        labels={{
          title: t(locale, "common.auth.captchaModalTitle"),
          verifying: t(locale, "common.auth.captchaVerifying"),
          instruction: t(locale, "common.auth.captchaInstruction"),
          success: t(locale, "common.auth.captchaSuccess"),
          drag: t(locale, "common.auth.captchaDrag")
        }}
      />
    </div>
  );
}
