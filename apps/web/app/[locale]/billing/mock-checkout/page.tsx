"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { CheckCircle2, Loader2, XCircle } from "lucide-react";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { API_URL } from "@/lib/api";
import { withLocale } from "@/i18n/routing";

function MockCheckoutInner() {
  const locale = useLocale();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [status, setStatus] = useState<"processing" | "success" | "error">("processing");
  const [error, setError] = useState("");

  useEffect(() => {
    const session = searchParams.get("session");
    const plan = searchParams.get("plan");
    if (!session || !plan) {
      setStatus("error");
      setError("Missing session or plan parameter");
      return;
    }

    let cancelled = false;

    fetch(`${API_URL}/billing/mock-upgrade`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ plan_name: plan }),
    })
      .then(async (response) => {
        if (!response.ok) {
          const text = await response.text();
          throw new Error(text || `HTTP ${response.status}`);
        }
        return response.json();
      })
      .then(() => {
        if (cancelled) return;
        setStatus("success");
        setTimeout(() => {
          router.push(withLocale(locale, "/billing/success"));
        }, 1500);
      })
      .catch((err) => {
        if (cancelled) return;
        setStatus("error");
        setError(err.message || "Mock upgrade failed");
      });

    return () => {
      cancelled = true;
    };
  }, [locale, router, searchParams]);

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <div className="w-full max-w-md border border-border-pg bg-bg-panel p-6 text-center rounded-2xl">
        {status === "processing" && (
          <>
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-text-pg" />
            <h1 className="mt-4 text-xl font-semibold">
              {locale === "zh" ? "正在处理订阅..." : "Processing subscription..."}
            </h1>
            <p className="mt-2 text-sm text-text-pg-muted">
              {locale === "zh" ? "请稍候，正在完成模拟升级。" : "Please wait while we complete your mock upgrade."}
            </p>
          </>
        )}
        {status === "success" && (
          <>
            <CheckCircle2 className="mx-auto h-8 w-8 text-status-positive" />
            <h1 className="mt-4 text-xl font-semibold">
              {locale === "zh" ? "订阅升级成功！" : "Subscription upgraded!"}
            </h1>
            <p className="mt-2 text-sm text-text-pg-muted">
              {locale === "zh" ? "即将跳转到成功页面..." : "Redirecting to success page..."}
            </p>
          </>
        )}
        {status === "error" && (
          <>
            <XCircle className="mx-auto h-8 w-8 text-status-negative" />
            <h1 className="mt-4 text-xl font-semibold">
              {locale === "zh" ? "模拟升级失败" : "Mock upgrade failed"}
            </h1>
            <p className="mt-3 text-sm text-text-pg-muted">{error}</p>
            <Link
              href={withLocale(locale, "/billing")}
              className="mt-5 inline-flex border border-border-pg px-4 py-2 text-sm text-text-pg hover:border-border-pg-strong rounded-lg"
            >
              {locale === "zh" ? "返回订阅页面" : "Back to Billing"}
            </Link>
          </>
        )}
      </div>
    </div>
  );
}

export default function MockCheckoutPage() {
  const locale = useLocale();
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[70vh] items-center justify-center">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      }
    >
      <MockCheckoutInner />
    </Suspense>
  );
}
