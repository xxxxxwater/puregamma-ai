"use client";

import { useEffect } from "react";
import { RefreshCw } from "lucide-react";

export default function SecretaryError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error("secretary_route_error", error);
  }, [error]);

  return (
    <div className="border border-border-pg bg-bg-panel p-6 rounded-2xl">
      <div className="text-xs font-semibold uppercase tracking-[0.18em] text-text-pg-muted">PRIVATE COMPANION</div>
      <h1 className="mt-3 text-xl font-semibold">亲密秘书暂时没有连接成功</h1>
      <p className="mt-2 text-sm leading-6 text-text-pg-muted">当前对话不会丢失，请重新连接。</p>
      <button type="button" onClick={reset} className="mt-5 inline-flex items-center gap-2 border border-border-pg-strong px-3 py-2 text-sm hover:bg-bg-panel-muted rounded-lg">
        <RefreshCw className="h-4 w-4" />重新连接
      </button>
    </div>
  );
}
