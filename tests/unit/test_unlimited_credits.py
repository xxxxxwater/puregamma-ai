import pytest

from apps.api.services.credit_service import InsufficientCreditsError, consume_credits


def test_credit_usage_blocks_when_balance_is_exhausted(db, demo_user):
    demo_user.credit_balance = 0
    db.commit()

    with pytest.raises(InsufficientCreditsError):
        consume_credits(db, demo_user.id, "metered_action", 30)
    assert demo_user.credit_balance == 0
