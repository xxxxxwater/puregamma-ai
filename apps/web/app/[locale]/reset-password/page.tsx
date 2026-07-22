"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { PasswordInput } from "@/components/password-input";
import { extractApiError, resetPassword } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t, type TranslationKey } from "@/lib/translations";

const PASSWORD_RULE_KEYS: Record<string, TranslationKey> = {
  length: "common.auth.passwordTooShort",
  common: "common.auth.passwordTooCommon",
  letter: "common.auth.passwordNeedLetter",
  digit: "common.auth.passwordNeedDigit",
  uppercase: "common.auth.passwordNeedUppercase",
};

export default function ResetPasswordPage() {
  const locale = useLocale();
  const zh = locale === "zh";
  const router = useRouter();
  const [token, setToken] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<"loading" | "form" | "success" | "error">("loading");
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    const tokenParam = new URLSearchParams(window.location.search).get("token");
    if (!tokenParam) { setStatus("error"); setErrorMsg(t(locale, "common.auth.resetLinkInvalid")); return; }
    setToken(tokenParam);
    setStatus("form");
  }, [locale]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || password.length < 8) return;
    setBusy(true);
    setErrorMsg("");
    try {
      await resetPassword(token, password);
      setStatus("success");
      setTimeout(() => router.push(`/${locale}/chat`), 3000);
    } catch (err: unknown) {
      const apiError = extractApiError(err);
      if (apiError.code === "INVALID_OR_EXPIRED_TOKEN") {
        setStatus("error");
        setErrorMsg(t(locale, "common.auth.resetLinkInvalid"));
      } else if (apiError.code === "PASSWORD_TOO_WEAK") {
        const ruleKey = apiError.rule ? PASSWORD_RULE_KEYS[apiError.rule] : undefined;
        setErrorMsg(ruleKey ? t(locale, ruleKey) : apiError.message || t(locale, "common.auth.passwordTooShort"));
      } else if (apiError.status === 429) {
        setErrorMsg(zh ? "操作过于频繁，请稍后再试" : "Too many attempts. Please try again later.");
      } else {
        setErrorMsg(t(locale, "common.auth.resetPasswordFailed"));
      }
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <div className="w-full max-w-md space-y-6">
        <div className="text-center">
          <Link href={withLocale(locale, "/")} className="inline-flex items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={32} height={32} className="mx-auto" />
            PureGamma AI
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{t(locale, "common.auth.resetPasswordTitle")}</h1>
        </div>

        <div className="space-y-4 border border-border-pg bg-bg-panel p-6">
          {status === "loading" ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <Loader2 className="h-8 w-8 animate-spin text-text-pg-muted" />
            </div>
          ) : status === "success" ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <CheckCircle className="h-8 w-8 text-status-positive" />
              <p className="text-sm text-text-pg">{t(locale, "common.auth.resetPasswordSuccess")}</p>
            </div>
          ) : status === "error" ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <XCircle className="h-8 w-8 text-status-negative" />
              <p className="text-sm text-status-negative">{errorMsg}</p>
              <Link href={withLocale(locale, "/forgot-password")} className="text-sm font-medium text-text-pg underline underline-offset-2">{t(locale, "common.auth.forgotPasswordTitle")}</Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-3">
              {errorMsg ? <p className="text-sm text-status-negative">{errorMsg}</p> : null}
              <PasswordInput value={password} onChange={setPassword} placeholder={t(locale, "common.auth.newPassword")} minLength={8} autoComplete="new-password" />
              <p className="text-xs text-text-pg-dim">{t(locale, "common.auth.passwordRequirements")}</p>
              <button type="submit" disabled={busy || !password || password.length < 8} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-text-pg px-4 py-2.5 text-sm font-semibold text-bg-panel transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
                {t(locale, "common.auth.resetPasswordTitle")}
              </button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
