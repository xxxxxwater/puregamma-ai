from __future__ import annotations

import pytest


@pytest.mark.contract
def test_secret_encryption_service_contract():
    pytest.xfail("No encryption/secret vault service exists yet for Plaid, exchange, wallet, or relay secrets.")


@pytest.mark.contract
def test_encrypted_secret_round_trip_contract():
    pytest.xfail("Implement a deterministic test interface for encrypt/decrypt with non-deterministic ciphertext and key rotation metadata.")


@pytest.mark.contract
def test_secret_values_are_not_serialized_contract():
    pytest.xfail("Add serializer tests once Plaid/exchange/wallet credential models and API schemas exist.")
