from __future__ import annotations

from sqlalchemy.orm import Session

from packages.agents.llm.provider_factory import get_llm_provider
from packages.reports.daily_market_report import render_daily_report


class ReportWriterAgent:
    def daily(self, research: dict, signals: list[dict], language: str = "en", *, user_id: str | None = None, db: Session | None = None) -> str:
        baseline = render_daily_report(research["market_regime"], research["quotes"], signals, language)
        prompt = (
            "Generate a concise institutional crypto daily brief using only this summarized context. "
            "Do not include secrets or personally identifying recipient data. Keep disclaimer.\n"
            f"Locale: {language}\nMarket regime: {research.get('market_regime')}\n"
            f"Risk summary: {research.get('risk_summary')}\nSignals: {signals[:3]}\n"
            f"Baseline report:\n{baseline}"
        )
        try:
            generated = get_llm_provider().complete(prompt, task_type="daily_market_report", locale=language, user_id=user_id, db=db)
        except Exception:
            return baseline
        disclaimer = "本内容仅供信息和研究参考，不构成投资建议。" if language == "zh" else "This is not financial advice."
        if disclaimer not in generated:
            generated = f"{generated.rstrip()}\n\n{disclaimer}"
        return generated if generated.lstrip().startswith("#") else baseline
