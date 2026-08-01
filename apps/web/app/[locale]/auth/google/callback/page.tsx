
"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Loader2 } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { googleCallback } from "@/lib/api";
import { withLocale } from "@/i18n/routing";
import { t } from "@/lib/translations";

function GoogleCallbackInner() {
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = searchParams.get("code");
    const state = searchParams.get("state");
    if (!code || !state) {
      setError(t(locale, "common.auth.googleCallbackError"));
      return;
    }
    let cancelled = false;
    googleCallback(code, state, locale)
      .then((result) => {
        if (cancelled) return;
        localStorage.setItem("pg_user", JSON.stringify(result.user));
        router.push(result.redirect_to || withLocale(locale, "/chat"));
      })
      .catch(() => {
        if (!cancelled) setError(t(locale, "common.auth.googleCallbackError"));
      });
    return () => {
      cancelled = true;
    };
  }, [locale, router, searchParams]);

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <div className="w-full max-w-md border border-border-pg bg-bg-panel p-6 text-center">
        {error ? (
          <>
            <h1 className="text-xl font-semibold">{t(locale, "common.auth.googleCallbackError")}</h1>
            <p className="mt-3 text-sm text-text-pg-muted">{error}</p>
            <Link href={withLocale(locale, "/login")} className="mt-5 inline-flex border border-border-pg px-4 py-2 text-sm text-text-pg hover:border-border-pg-strong">
              {t(locale, "common.nav.signin")}
            </Link>
          </>
        ) : (
          <>
            <Loader2 className="mx-auto h-5 w-5 animate-spin" />
            <h1 className="mt-4 text-xl font-semibold">{t(locale, "common.auth.googleProcessing")}</h1>
          </>
        )}
      </div>
    </div>
  );
}

export default function GoogleCallbackPage() {
  const locale = useLocale();
  return (
    <Suspense fallback={<div className="p-6 text-sm text-text-pg-muted">{t(locale, "common.auth.googleProcessing")}</div>}>
      <GoogleCallbackInner />
    </Suspense>
  );
}
