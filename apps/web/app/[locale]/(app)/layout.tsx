import type { ReactNode } from "react";
import { AppShell } from "@/components/nav";
import type { Locale } from "@/i18n/routing";

export default function AppLayout({ children, params }: { children: ReactNode; params: { locale: Locale } }) {
  return <AppShell locale={params.locale}>{children}</AppShell>;
}
