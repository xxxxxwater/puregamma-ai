"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { useLocale } from "@/components/i18n/LocaleProvider";
import { ErrorState, LoadingSkeleton } from "@/components/puregamma";
import { getMe } from "@/lib/api";
import { withLocale } from "@/i18n/routing";

export function AdminGate({ children }: { children: ReactNode }) {
  const locale = useLocale();
  const router = useRouter();
  const [state, setState] = useState<"loading" | "denied" | "ok">("loading");

  useEffect(() => {
    let active = true;
    getMe()
      .then((result) => {
        if (!active) return;
        const role = String(result.user?.role ?? "").toLowerCase();
        setState(role === "admin" ? "ok" : "denied");
      })
      .catch((reason: Error & { status?: number }) => {
        if (!active) return;
        if (reason.status === 401) {
          router.replace(`${withLocale(locale, "/login")}?returnTo=${encodeURIComponent(withLocale(locale, "/admin"))}`);
        } else {
          setState("denied");
        }
      });
    return () => {
      active = false;
    };
  }, [locale, router]);

  if (state === "loading") return <LoadingSkeleton />;
  if (state === "denied") {
    const zh = locale === "zh";
    return (
      <ErrorState
        title={zh ? "需要管理员权限" : "Administrator access required"}
        description={zh ? "当前账户没有访问管理后台的权限。如有需要，请联系团队管理员。" : "Your account does not have permission to view the admin console. Contact your team administrator if you believe this is a mistake."}
      />
    );
  }
  return <>{children}</>;
}
