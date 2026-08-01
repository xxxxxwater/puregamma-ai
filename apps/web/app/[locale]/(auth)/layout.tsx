import type { Metadata } from "next";
import type { ReactNode } from "react";
import { isLocale } from "@/i18n/routing";

export async function generateMetadata({ params }: { params: { locale: string } }): Promise<Metadata> {
  if (!isLocale(params.locale)) return {};
  const zh = params.locale === "zh";
  return {
    title: zh ? "账户 | PureGamma AI" : "Account | PureGamma AI",
    description: zh ? "登录或创建 PureGamma AI 账户。" : "Sign in or create a PureGamma AI account.",
    robots: { index: false, follow: false }
  };
}

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="relative min-h-dvh">
      <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col justify-center px-6 py-12">{children}</div>
    </div>
  );
}
