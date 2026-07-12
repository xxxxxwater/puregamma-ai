import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import type { Locale } from "@/i18n/routing";
export default function RiskPage({ params }: { params: { locale: Locale } }) { return <StrategyRuntimeConsole locale={params.locale} view="risk" />; }
