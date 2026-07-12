from __future__ import annotations

from apps.api.config import Settings
from packages.agents.llm.provider_factory import get_llm_provider, llm_status
from packages.database.models import LLMCallLog


def test_deepseek_missing_key_falls_back_to_mock_and_logs_redacted_prompt(db, demo_user):
    settings = Settings(llm_provider="deepseek", deepseek_api_key="", deepseek_model="deepseek-v4-flash")
    status = llm_status(settings)

    provider = get_llm_provider(settings)
    content = provider.complete(
        "Generate BTC brief. DEEPSEEK_API_KEY=sk-testsecret123 phone +1 555 555 0100",
        task_type="deepseek_report_generation",
        locale="zh",
        user_id=demo_user.id,
        db=db,
    )
    db.commit()
    log = db.query(LLMCallLog).order_by(LLMCallLog.created_at.desc()).first()

    assert status["provider"] == "deepseek"
    assert status["active_provider"] == "mock"
    assert status["model"] == "deepseek-v4-flash"
    assert status["configured"] is False
    assert "Users bear all risks of using this service. The service provider is not responsible for any AI-generated content." in content
    assert log.status == "fallback_mock"
    assert "[REDACTED]" in log.prompt_summary
    assert "sk-testsecret123" not in log.prompt_summary
    assert "+1 555 555 0100" not in log.prompt_summary


def test_deepseek_status_reports_configured_provider_without_calling_network():
    settings = Settings(llm_provider="deepseek", deepseek_api_key="test-only", deepseek_model="deepseek-v4-flash")
    status = llm_status(settings)

    assert status["provider"] == "deepseek"
    assert status["active_provider"] == "deepseek"
    assert status["configured"] is True
    assert status["model"] == "deepseek-v4-flash"
