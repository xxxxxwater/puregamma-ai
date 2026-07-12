import { StrategyRuntimeConsole } from "@/components/strategy-runtime-console";
import type { Locale } from "@/i18n/routing";
export default function StrategyDetailPage({ params }: { params: { locale: Locale; strategyId: string } }) { return <StrategyRuntimeConsole locale={params.locale} view="detail" strategyId={params.strategyId} />; }
