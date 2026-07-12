from apps.api.services.credit_service import consume_credits, refund_credits


def test_credit_usage_does_not_block_or_change_balance(db, demo_user):
    demo_user.credit_balance = 0
    db.commit()

    debit = consume_credits(db, demo_user.id, "unlimited_action", 30)
    refund = refund_credits(db, demo_user.id, "unlimited_action", 30)

    assert debit.credits_delta == 0
    assert refund.credits_delta == 0
    assert demo_user.credit_balance == 0
    assert debit.metadata_json["credits_bypassed"] == 30
