"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import { Bell, Chrome, Loader2 } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { googleLogin } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export default function SignUpPage() {
  const locale = useLocale();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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

  return (
    <div className="flex min-h-[80vh] items-center justify-center">
      <div className="w-full max-w-md space-y-8">
        <div className="text-center">
          <Link href={withLocale(locale, "/")} className="inline-flex items-center gap-2 font-semibold text-text-pg">
            <Image src="/logo.png" alt="PureGamma" width={24} height={24} />
            PureGamma AI
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{zh ? "创建账户" : "Create your account"}</h1>
          <p className="mt-2 text-sm text-text-pg-muted">{zh ? "使用 Google 创建并验证你的账户。" : "Create and verify your account with Google."}</p>
        </div>

        <div className="space-y-4 border border-border-pg bg-bg-panel p-6">
          {error ? <p className="border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm text-status-negative">{error}</p> : null}
          <button type="button" disabled={busy} onClick={handleGoogleLogin} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm font-semibold text-text-pg transition hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-50">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Chrome className="h-4 w-4" />}
            {t(locale, "common.auth.googleLogin")}
          </button>
        </div>

        <p className="text-center text-xs text-text-pg-dim">
          {zh ? "创建账户即表示你同意服务条款与隐私政策。使用该服务用户自行承担风险。提供本服务的主体概不负责AI生成内容。" : "By creating an account you agree to our Terms of Service and Privacy Policy. Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."}
        </p>
      </div>
    </div>
  );
}
