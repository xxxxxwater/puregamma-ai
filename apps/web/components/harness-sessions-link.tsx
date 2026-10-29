import { harnessSessionsUrl } from "@/lib/harness-sessions";
import type { Locale } from "@/i18n/routing";

/** "Open Harness sessions": rendered only when the session broker is enabled for this build. */
export function HarnessSessionsLink({ locale }: { locale: Locale }) {
  const href = harnessSessionsUrl();
  if (!href) return null;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      data-testid="harness-sessions-link"
      className="ml-auto inline-flex min-h-[44px] items-center text-xs font-medium text-muted underline-offset-4 hover:text-foreground hover:underline md:min-h-0"
    >
      {locale === "zh" ? "打开 Harness 会话" : "Open Harness sessions"}
    </a>
  );
}
