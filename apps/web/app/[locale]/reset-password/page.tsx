"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { resetPassword } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";

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
    const t = new URLSearchParams(window.location.search).get("token");
    if (!t) { setStatus("error"); setErrorMsg("Missing token"); return; }
    setToken(t);
    setStatus("form");
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || password.length < 8) return;
    setBusy(true);
    setErrorMsg("");
    try {
      await resetPassword(token, password);
      setStatus("success");
      setTimeout(() => router.push(`/${locale}/chat`), 3000);
    } catch {
      setErrorMsg(t(locale, "common.auth.verifyEmailError"));
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
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder={t(locale, "common.auth.newPassword")} className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong" required minLength={8} />
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
