"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Loader2, CheckCircle, XCircle } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { emailVerify, resendVerificationEmail } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export default function VerifyEmailPage() {
  const locale = useLocale();
  const router = useRouter();
  const [status, setStatus] = useState<"loading" | "success" | "error">("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const [resending, setResending] = useState(false);
  const [resent, setResent] = useState(false);
  const [resendEmail, setResendEmail] = useState("");
  const zh = locale === "zh";

  useEffect(() => {
    const token = new URLSearchParams(window.location.search).get("token");
    if (!token) {
      setStatus("error");
      setErrorMessage(t(locale, "common.auth.verifyEmailError"));
      return;
    }
    emailVerify(token)
      .then(() => {
        setStatus("success");
        setTimeout(() => router.push(`/${locale}/chat`), 3000);
      })
      .catch(() => {
        setStatus("error");
        setErrorMessage(t(locale, "common.auth.verifyEmailError"));
      });
  }, [locale, router]);

  const handleResend = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!resendEmail) return;
    setResending(true);
    try {
      await resendVerificationEmail(resendEmail);
      setResent(true);
    } catch {
      setErrorMessage(zh ? "发送失败，请稍后重试" : "Failed to send. Please try again later.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <div className="w-full max-w-md space-y-6 text-center">
        <div className="text-center">
          <Link href={withLocale(locale, "/")} className="inline-flex items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={32} height={32} className="mx-auto" />
            PureGamma AI
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{t(locale, "common.auth.verifyEmailTitle")}</h1>
        </div>

        <div className="space-y-4 border border-border-pg bg-bg-panel p-6">
          {status === "loading" ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <Loader2 className="h-8 w-8 animate-spin text-text-pg-muted" />
              <p className="text-sm text-text-pg-muted">{t(locale, "common.auth.verifyEmailDescription")}</p>
            </div>
          ) : status === "success" ? (
            <div className="flex flex-col items-center gap-3 py-4">
              <CheckCircle className="h-8 w-8 text-status-positive" />
              <p className="text-sm text-text-pg">{t(locale, "common.auth.verifyEmailSuccess")}</p>
              <p className="text-xs text-text-pg-muted">{zh ? "即将跳转到控制台..." : "Redirecting to chat..."}</p>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-3 py-4">
              <XCircle className="h-8 w-8 text-status-negative" />
              <p className="text-sm text-status-negative">{errorMessage}</p>
              {!resent ? (
                <form onSubmit={handleResend} className="flex w-full flex-col items-center gap-3">
                  <input
                    type="email"
                    value={resendEmail}
                    onChange={(e) => setResendEmail(e.target.value)}
                    placeholder={t(locale, "common.auth.emailPlaceholder")}
                    className="w-full border border-border-pg bg-bg-panel-muted px-3 py-2 text-sm text-text-pg placeholder:text-text-pg-dim outline-none focus:border-border-pg-strong"
                    required
                  />
                  <button
                    type="submit"
                    disabled={resending || !resendEmail}
                    className="inline-flex items-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2 text-sm font-medium text-text-pg transition hover:border-border-pg-strong disabled:opacity-50"
                  >
                    {resending ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
                    {t(locale, "common.auth.resendVerification")}
                  </button>
                </form>
              ) : (
                <p className="text-sm text-text-pg">{t(locale, "common.auth.verificationResent")}</p>
              )}
            </div>
          )}
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
