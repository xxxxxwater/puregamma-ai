from __future__ import annotations

from sqlalchemy.orm import Session

from apps.api.services.daily_brief_service import gather_context, generate_daily_brief
from packages.reports.daily_market_report import render_daily_report


class ReportWriterAgent:
    def daily(self, research: dict, signals: list[dict], language: str = "en", *, user_id: str | None = None, db: Session | None = None) -> str:
        if user_id and db:
            try:
                return generate_daily_brief(db, user_id, language)
            except Exception:
                pass
        return _llm_daily_fallback(research, signals, language, user_id, db)

    def daily_brief(self, db: Session, user_id: str, language: str) -> str:
        return generate_daily_brief(db, user_id, language)


def _llm_daily_fallback(
    research: dict,
    signals: list[dict],
    language: str,
    user_id: str | None = None,
    db: Session | None = None,
) -> str:
    baseline = render_daily_report(research["market_regime"], research["quotes"], signals, language)

    if language == "zh":
        prompt = (
            "用中文撰写一份200字以内的每日简报。直接输出，不用 # 标题。\n"
            f"市场: {research.get('market_regime')}\n"
            f"风险: {research.get('risk_summary')}\n"
            f"信号: {signals[:3]}\n"
            f"基线:\n{baseline}"
        )
    else:
        prompt = (
            "Write a concise daily brief under 200 words. Direct output, no # headings.\n"
            f"Market: {research.get('market_regime')}\n"
            f"Risk: {research.get('risk_summary')}\n"
            f"Signals: {signals[:3]}\n"
            f"Baseline:\n{baseline}"
        )

    try:
        from packages.agents.llm.provider_factory import get_llm_provider
        generated = get_llm_provider().complete(
            prompt,
            task_type="daily_market_report",
            locale=language,
            user_id=user_id,
            db=db,
        )
    except Exception:
        return baseline

    disclaimer = "使用该服务用户自行承担风险 提供本服务的主体概不负责AI生成所有责任。" if language == "zh" else "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content."
    if disclaimer not in generated:
        generated = f"{generated.rstrip()}\n\n{disclaimer}"
    return generated if generated.lstrip().startswith("#") else baseline
