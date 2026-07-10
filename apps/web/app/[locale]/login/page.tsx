"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowRight, Bell, Chrome, Loader2, Mail } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { googleLogin, mockLogin } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";

export default function LoginPage() {
  const locale = useLocale();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const zh = locale === "zh";

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!email.trim()) { setError(zh ? "请输入 Email。" : "Email is required."); return; }
    setBusy(true);
    setError("");
    try {
      const result = await mockLogin(email.trim(), undefined, "user");
      localStorage.setItem("pg_user", JSON.stringify(result.user));
      router.push(withLocale(locale, "/dashboard"));
    } catch {
      setError(zh ? "登录失败，请检查 Email 后重试。" : "Login failed. Please check your email and try again.");
    } finally {
      setBusy(false);
    }
  };

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
            <Bell className="h-6 w-6 text-text-pg" />
            PureGamma.ai
          </Link>
          <h1 className="mt-6 text-2xl font-semibold">{zh ? "欢迎回来" : "Welcome back"}</h1>
          <p className="mt-2 text-sm text-text-pg-muted">{zh ? "登录投研控制台。" : "Sign in to your research console."}</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 border border-border-pg bg-bg-panel p-6">
          <label className="block">
            <span className="mb-1.5 block text-sm font-medium text-text-pg-muted">Email</span>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-pg-muted" />
              <input
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                placeholder="you@example.com"
                className="w-full border border-border-pg bg-bg-panel-muted py-2.5 pl-10 pr-3 text-sm text-text-pg placeholder:text-text-pg-dim focus:border-border-pg-strong focus:outline-none"
              />
            </div>
          </label>

          {error ? <p className="border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm text-status-negative">{error}</p> : null}

          <button type="submit" disabled={busy} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-2.5 text-sm font-semibold text-pg-black transition hover:bg-pg-white-soft disabled:cursor-not-allowed disabled:opacity-50">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            {busy ? (zh ? "登录中..." : "Signing in...") : t(locale, "common.nav.signin")}
            {!busy ? <ArrowRight className="h-4 w-4" /> : null}
          </button>

          <p className="text-center text-xs text-text-pg-muted">
            {zh ? "首次使用 PureGamma？" : "New to PureGamma?"}{" "}
            <Link href={withLocale(locale, "/signup")} className="text-text-pg hover:underline">{zh ? "创建账户" : "Create an account"}</Link>
          </p>

          <div className="flex items-center gap-3 pt-2">
            <div className="h-px flex-1 bg-border-pg" />
            <span className="text-xs text-text-pg-muted">{t(locale, "common.auth.orUseGoogle")}</span>
            <div className="h-px flex-1 bg-border-pg" />
          </div>

          <button type="button" disabled={busy} onClick={handleGoogleLogin} className="inline-flex w-full items-center justify-center gap-2 border border-border-pg bg-bg-panel-muted px-4 py-2.5 text-sm font-semibold text-text-pg transition hover:border-border-pg-strong disabled:cursor-not-allowed disabled:opacity-50">
            <Chrome className="h-4 w-4" />
            {t(locale, "common.auth.googleLogin")}
          </button>
        </form>

        <div className="border border-border-pg bg-bg-panel-muted p-4 text-center">
          <p className="text-xs text-text-pg-muted">
            <span className="font-medium text-status-warning">{t(locale, "common.badges.mockMode")}</span> {zh ? "输入任意 Email 即可在开发环境中登录。" : "Enter any email to sign in instantly during development."}
          </p>
        </div>
      </div>
    </div>
  );
}
