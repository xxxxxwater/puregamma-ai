from __future__ import annotations

from dataclasses import replace

from apps.api.config import Settings
from packages.workers import scheduler as scheduler_module


def test_enabled_market_and_onchain_providers_are_actually_scheduled(monkeypatch):
    settings = replace(
        Settings(),
        data_sync_worker_enabled=True,
        binance_public_data_enabled=True,
        defillama_free_enabled=True,
        the_graph_enabled=True,
        onchain_rpc_enabled=True,
        binance_sync_interval_minutes=7,
        defillama_sync_interval_minutes=181,
        onchain_sync_interval_minutes=17,
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)

    scheduler = scheduler_module.build_scheduler()
    jobs = {job.id: job for job in scheduler.get_jobs()}

    assert "provider_binance_market_sync" in jobs
    assert "provider_defillama_sync" in jobs
    assert "provider_the_graph_sync" in jobs
    assert "provider_evm_rpc_sync" in jobs

    assert jobs["provider_binance_market_sync"].trigger.interval.total_seconds() == 7 * 60
    assert jobs["provider_defillama_sync"].trigger.interval.total_seconds() == 181 * 60
    assert jobs["provider_the_graph_sync"].trigger.interval.total_seconds() == 17 * 60
    assert jobs["provider_evm_rpc_sync"].trigger.interval.total_seconds() == 17 * 60


def test_disabled_optional_providers_do_not_get_background_jobs(monkeypatch):
    settings = replace(
        Settings(),
        data_sync_worker_enabled=True,
        defillama_free_enabled=False,
        the_graph_enabled=False,
        onchain_rpc_enabled=False,
    )
    monkeypatch.setattr(scheduler_module, "get_settings", lambda: settings)

    scheduler = scheduler_module.build_scheduler()
    jobs = {job.id for job in scheduler.get_jobs()}

    assert "provider_defillama_sync" not in jobs
    assert "provider_the_graph_sync" not in jobs
    assert "provider_evm_rpc_sync" not in jobs
