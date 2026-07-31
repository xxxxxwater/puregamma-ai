# Acceptance map — scenarios A–K

Final verification slice. Every scenario maps to covering tests; scenarios
already covered by existing suites are referenced (and were re-run green),
gaps are closed in `tests/acceptance/test_scenarios.py`.

Run the acceptance layer (load smoke deselected by default):

```powershell
.venv\Scripts\python.exe -m pytest tests/acceptance -q
```

Run everything including the opt-in load smoke (Scenario K):

```powershell
.venv\Scripts\python.exe -m pytest tests/acceptance -q --runload
```

`--runload` is registered in `tests/acceptance/conftest.py`; pytest.ini is
untouched and `@pytest.mark.load` tests are skipped in the default suite.

## Scenario map

| # | Scenario (what it proves) | Covering test(s) | Status |
|---|---|---|---|
| A | `/api/research/today` contract: `overnight_events` carry source provider/published_at/freshness, `actions` ≤ 3, `next_event` present; unauth → 401 | `tests/integration/test_research_api.py::test_today_requires_authentication`, `::test_today_contract_keys`, `::test_upcoming_events_and_task_rerun_idempotent` + NEW `tests/acceptance/test_scenarios.py::test_scenario_a_today_payload_content` (payload-content gap) | Covered + NEW complement |
| B | Billing exactly-once: signed checkout/renewal/refund processed once, forged webhook rejected, credit reserve/settle/refund idempotency, plan channel matrix, prod guards | `tests/integration/test_billing_acceptance.py` (17 tests, incl. `test_duplicate_signed_webhook_delivery_is_processed_once`, `test_settle_retry_charges_exactly_once`, `test_stream_failure_refund_restores_balance_exactly_once`) | Covered |
| C | Event alert exactly-once: user with holdings + matching MarketEvent → alert path run twice → 1 Alert, 1 NotificationDelivery per channel, rerun → zero new rows | NEW `tests/acceptance/test_scenarios.py::test_scenario_c_event_alert_exactly_once` (uses the NEW `research_event_service.create_alert_for_event`; see note below) | NEW |
| D | Execution chain: signal → risk → intent → fill → position/pnl → reconcile; order idempotency; kill switch; restart recovery | `tests/integration/test_execution_chain.py` (9 tests, incl. `test_signal_order_idempotency_dedup`, `test_restart_recovery_between_fill_and_reconcile`) | Covered |
| E | Custody accounting: deposit confirm idempotent, withdrawal hold/cancel, tenant scoping, fills settle/freeze custody, production guard | `tests/integration/test_custody_api.py` (15 tests, incl. `test_deposit_confirm_testnet_idempotent`, `test_withdrawals_are_tenant_scoped`) | Covered |
| F | Agent answer envelopes on the SSE fast path (evidence-grounded, envelope before completion) + SSE time-to-first-event < 2s | `tests/integration/test_agent_answer_api.py` (5 tests) + NEW `tests/acceptance/test_scenarios.py::test_scenario_sse_first_event_under_two_seconds` | Covered + NEW complement |
| G | Daily digest fan-out exactly-once at a shared minute: 8 users × 2 channels × report types, exact Report/Delivery counts, second run zero new rows; failure backoff, daily-limit terminal | `tests/workers/test_daily_orchestrator.py::test_eight_users_same_minute_exactly_once` (superset: 8 users × [email, telegram] + web inbox × 4 report types), `::test_daily_limit_error_advances_to_next_slot_without_retry_loop`, `::test_generic_failure_applies_growing_backoff` | Covered (superset of the 2-type shape — not duplicated) |
| H | Model routing: three task types → three provider logs (deepseek fast / luna review / kimi synthesis); kimi unconfigured → degraded with real log; never mock in production | `tests/unit/test_model_router.py::test_deep_research_flow_orders_models_and_surfaces_disagreements`, `::test_kimi_provider_chat_success_logs_call`, `::test_router_degrades_to_deepseek_when_kimi_unconfigured`, `::test_router_raises_and_never_uses_mock_in_production`, `::test_route_for_task_maps_documented_task_types` | Covered |
| I | Admin console: overview counts, users, reports, deliveries, research events/impacts, alerts, LLM calls, workers; non-admin forbidden; no credential leakage | `tests/integration/test_admin_console.py` (19 tests) | Covered |
| J | Research engine rerun-safety: fingerprint dedup, price-move thresholds, asset/user impacts + actions exactly-once, provider failure → degraded health | `tests/unit/test_research_engine.py` (6 tests, incl. `test_build_is_rerun_safe_via_fingerprint_dedup`, `test_user_portfolio_impacts_and_actions_with_synthetic_holdings`) | Covered |
| K | Scale smoke: 300 users due the same minute; orchestrator rerun → exactly one Report per (user,type,local_date), one NotificationDelivery per (user,channel,type), wall time recorded (< 15 min), failure_count ≤ 1 | NEW `tests/acceptance/test_scenarios.py::test_scenario_k_scale_smoke_300_users_same_minute` — **opt-in**: `--runload` (marked `load`) | NEW (opt-in) |

## Notes / deviations

- **Scenario C path**: no alert-generation path from events existed
  (`scan_market_anomalies` → `scan_signals` only writes `Signal` rows and
  touches the network; the research pipeline stopped at impacts/actions).
  The minimal path was implemented as specified:
  `research_event_service.create_alert_for_event(db, event, ...)`. One
  `Alert` per (user, event) with idempotency key `event-alert:{user}:{event}`;
  one `NotificationDelivery` per selected channel with idempotency key
  `event-alert:{user}:{event}:{channel}` — the dispatcher is exactly-once on
  that key, so reruns create zero new rows.
- **Scenario K wording**: the production orchestrator caps one run at 100 due
  preferences (batch safety), so 300 users drain in 3 waves + 1 empty
  verification pass; the explicit rerun after the drain is the exactly-once
  pass. All assertions (a)–(d) hold as specified. Measured: 4 waves, drain
  ≈ 16 s on this machine, SSE first event ≈ 0.05 s.
- **Scenario G**: the existing orchestrator test already covers a superset
  (4 default report types and the always-on web inbox on top of the 2
  configured channels), so it is referenced rather than duplicated.
- UTC everywhere; idempotency asserted by row counts, never by mocks alone.
