"use client";

import { Suspense, useState } from "react";
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
  const [status, setStatus] = useState<"confirm" | "processing" | "success" | "error">("confirm");
  const [error, setError] = useState("");

  const session = searchParams.get("session");
  const plan = searchParams.get("plan") || "";

  const confirmUpgrade = async () => {
    setStatus("processing");
    setError("");
    try {
      const response = await fetch(`${API_URL}/billing/mock-upgrade`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ plan_name: plan }),
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `HTTP ${response.status}`);
      }
      setStatus("success");
      setTimeout(() => {
        router.push(withLocale(locale, "/billing/success?mode=mock"));
      }, 1500);
    } catch (err) {
      setStatus("error");
      setError(err instanceof Error ? err.message : "Mock upgrade failed");
    }
  };

  const zh = locale === "zh";

  return (
    <div className="flex min-h-[70vh] items-center justify-center px-4">
      <div className="w-full max-w-md border border-border-pg bg-bg-panel p-6 text-center">
        {status === "confirm" && (
          <>
            <h1 className="text-xl font-semibold">{zh ? "确认模拟升级" : "Confirm mock upgrade"}</h1>
            {!session || !plan ? (
              <>
                <p className="mt-3 text-sm text-status-negative">{zh ? "缺少会话或套餐参数。" : "Missing session or plan parameter."}</p>
                <Link href={withLocale(locale, "/billing")} className="mt-5 inline-flex border border-border-pg px-4 py-2 text-sm text-text-pg hover:border-border-pg-strong">
                  {zh ? "返回订阅页面" : "Back to Billing"}
                </Link>
              </>
            ) : (
              <>
                <div className="mt-4 space-y-2 border border-border-pg bg-bg-panel-muted p-4 text-left text-sm">
                  <div className="flex items-center justify-between"><span className="text-text-pg-muted">{zh ? "套餐" : "Plan"}</span><span className="font-semibold">{plan}</span></div>
                  <div className="flex items-center justify-between"><span className="text-text-pg-muted">{zh ? "模式" : "Mode"}</span><span>{zh ? "模拟（不产生真实扣费）" : "Mock (no real charge)"}</span></div>
                </div>
                <button type="button" onClick={() => void confirmUpgrade()} className="mt-5 inline-flex w-full items-center justify-center gap-2 border border-border-pg-strong bg-pg-white px-4 py-2.5 text-sm font-semibold text-pg-black hover:bg-pg-white-soft">
                  {zh ? "确认升级" : "Confirm upgrade"}
                </button>
                <Link href={withLocale(locale, "/billing")} className="mt-3 inline-block text-xs text-text-pg-muted hover:text-text-pg">
                  {zh ? "取消，返回订阅页面" : "Cancel and back to billing"}
                </Link>
              </>
            )}
          </>
        )}
        {status === "processing" && (
          <>
            <Loader2 className="mx-auto h-6 w-6 animate-spin text-text-pg" />
            <h1 className="mt-4 text-xl font-semibold">
              {zh ? "正在处理订阅..." : "Processing subscription..."}
            </h1>
            <p className="mt-2 text-sm text-text-pg-muted">
              {zh ? "请稍候，正在完成模拟升级。" : "Please wait while we complete your mock upgrade."}
            </p>
          </>
        )}
        {status === "success" && (
          <>
            <CheckCircle2 className="mx-auto h-8 w-8 text-status-positive" />
            <h1 className="mt-4 text-xl font-semibold">
              {zh ? "订阅升级成功！" : "Subscription upgraded!"}
            </h1>
            <p className="mt-2 text-sm text-text-pg-muted">
              {zh ? "即将跳转到成功页面..." : "Redirecting to success page..."}
            </p>
          </>
        )}
        {status === "error" && (
          <>
            <XCircle className="mx-auto h-8 w-8 text-status-negative" />
            <h1 className="mt-4 text-xl font-semibold">
              {zh ? "模拟升级失败" : "Mock upgrade failed"}
            </h1>
            <p className="mt-3 text-sm text-text-pg-muted">{error}</p>
            <button type="button" onClick={() => setStatus("confirm")} className="mt-5 inline-flex border border-border-pg px-4 py-2 text-sm text-text-pg hover:border-border-pg-strong">
              {zh ? "重试" : "Retry"}
            </button>
            <Link href={withLocale(locale, "/billing")} className="mt-3 block text-xs text-text-pg-muted hover:text-text-pg">
              {zh ? "返回订阅页面" : "Back to Billing"}
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
