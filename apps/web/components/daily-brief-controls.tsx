"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Languages, LoaderCircle } from "lucide-react";
import { API_URL } from "@/lib/api";
import { Button } from "@/components/ui";

export function DailyBriefControls({ locale }: { locale: "en" | "zh" }) {
  const [busy, setBusy] = useState<"en" | "zh" | null>(null);
  const [failed, setFailed] = useState(false);
  const router = useRouter();
  const label = locale === "zh" ? { zh: "生成中文日报", en: "Generate English" } : { zh: "生成中文日报", en: "Generate English" };
  const generate = async (language: "en" | "zh") => {
    setBusy(language);
    setFailed(false);
    try {
      const response = await fetch(`${API_URL}/reports/daily?locale=${language}`, { method: "POST", credentials: "include", headers: { "X-PG-Locale": language } });
      if (!response.ok) throw new Error("Daily brief generation failed");
      router.refresh();
    } catch {
      setFailed(true);
    } finally {
      setBusy(null);
    }
  };
  return <div className="flex items-center gap-2"><Button variant="secondary" disabled={busy !== null} onClick={() => generate("zh")}><Languages className="h-4 w-4" />{busy === "zh" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}{label.zh}</Button><Button variant="secondary" disabled={busy !== null} onClick={() => generate("en")}><Languages className="h-4 w-4" />{busy === "en" ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}{label.en}</Button>{failed ? <span className="text-xs text-status-negative">{locale === "zh" ? "生成失败，请稍后重试" : "Generation failed. Please try again."}</span> : null}</div>;
}
