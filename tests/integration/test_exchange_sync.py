from __future__ import annotations

import pytest


@pytest.mark.contract
def test_read_only_exchange_key_saved_encrypted_contract():
    pytest.xfail("No exchange credential service exists yet. Expected: read-only keys encrypted at rest and redacted from API responses.")


@pytest.mark.contract
def test_withdrawal_permission_warning_contract():
    pytest.xfail("No exchange permission validator exists yet. Expected: withdrawal permissions raise a warning/block.")


@pytest.mark.contract
def test_exchange_balances_and_trades_normalize_contract():
    pytest.xfail("No exchange sync normalizer exists yet. Expected: balances/trades normalize and one exchange failure does not stop other sources.")


@pytest.mark.contract
def test_private_key_or_seed_phrase_rejected_contract():
    pytest.xfail("No credential intake validator exists yet. Expected: private keys/seed phrases are rejected.")
