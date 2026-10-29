"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui";

/**
 * Route-level error boundary for every localized page.
 *
 * Without it a render error on any page except Secretary fell through to
 * Next's default error screen, outside the app shell. This keeps the shell,
 * says plainly that nothing was submitted by showing this page, offers a
 * retry and a way back, and shows only the opaque digest - never a stack or
 * server message.
 */
export default function LocaleRouteError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  const params = useParams<{ locale?: string }>();
  const zh = params?.locale === "zh";
  useEffect(() => {
    console.error("route_error", error.digest || error.name);
  }, [error]);

  return (
    <section role="alert" className="mx-auto mt-6 max-w-xl rounded-2xl border border-border-pg bg-bg-panel p-6" data-testid="route-error">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-text-pg-muted">PureGamma AI</p>
      <h1 className="mt-3 text-xl font-semibold">{zh ? "这个页面暂时无法显示" : "This page could not be displayed"}</h1>
      <p className="mt-2 text-sm leading-6 text-text-pg-muted">
        {zh
          ? "页面在显示时出错。这不会提交任何订单或修改你的账户；重新加载后会读取服务端的最新状态。"
          : "Something went wrong while showing this page. Showing it submits no order and changes nothing in your account; retrying reads the latest state from the server."}
      </p>
      {error.digest ? <p className="mt-3 font-mono text-xs text-text-pg-dim">{zh ? "参考编号" : "Reference"}: {error.digest}</p> : null}
      <div className="mt-5 flex flex-wrap gap-2">
        <Button variant="primary" type="button" onClick={reset} className="inline-flex min-h-10 items-center gap-2 rounded-lg px-4 text-sm font-semibold hover:opacity-90">
          <RefreshCw className="h-4 w-4" aria-hidden />
          {zh ? "重试" : "Try again"}
        </Button>
        <Link href={`/${zh ? "zh" : "en"}/dashboard`} className="inline-flex min-h-10 items-center rounded-lg border border-border-pg px-4 text-sm hover:border-border-pg-strong">
          {zh ? "返回工作台" : "Back to the workspace"}
        </Link>
      </div>
    </section>
  );
}
