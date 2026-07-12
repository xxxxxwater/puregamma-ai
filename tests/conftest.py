from __future__ import annotations

import json
import os
import sys
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from apps.api.dependencies import create_access_token, get_db  # noqa: E402
from apps.api.main import app  # noqa: E402
from packages.database.models import Base, User, UserPreference  # noqa: E402
from packages.database.seed import seed_all  # noqa: E402


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    seed_all(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)


@pytest.fixture()
def demo_user(db) -> User:
    return db.query(User).filter(User.email == "demo@puregamma.ai").one()


@pytest.fixture()
def user_factory(db):
    def _create(
        email: str,
        *,
        role: str = "user",
        plan: str = "Free",
        credit_balance: int = 30,
        channels: list[str] | None = None,
    ) -> User:
        user = User(email=email, name=email.split("@")[0], role=role, plan=plan, credit_balance=credit_balance)
        db.add(user)
        db.flush()
        db.add(
            UserPreference(
                user_id=user.id,
                email_recipient=email,
                telegram_chat_id="mock-telegram-chat",
                slack_webhook_url="mock-slack-webhook",
                imessage_recipient="+15555550100",
                notification_channels=channels or ["email", "telegram", "slack", "imessage"],
            )
        )
        db.commit()
        db.refresh(user)
        return user

    return _create


@pytest.fixture()
def pro_user(user_factory) -> User:
    return user_factory("pro-user@puregamma.ai", plan="Pro", credit_balance=1000)


@pytest.fixture()
def max_user(user_factory) -> User:
    return user_factory("max-user@puregamma.ai", plan="Max", credit_balance=10000)


@pytest.fixture()
def normal_user(user_factory) -> User:
    return user_factory("normal-user@puregamma.ai", plan="Free", credit_balance=30)


@pytest.fixture()
def admin_user(user_factory) -> User:
    return user_factory("admin-user@puregamma.ai", role="admin", plan="Max", credit_balance=10000)


@pytest.fixture()
def api_client(db):
    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def auth_headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user)}"}


def stripe_event(event_id: str, event_type: str, obj: dict) -> tuple[dict, bytes]:
    event = {"id": event_id, "type": event_type, "data": {"object": obj}}
    return event, json.dumps(event, separators=(",", ":")).encode()


@pytest.fixture()
def hmac_payload():
    body = b'{"recipient":"+15555550100","message":"hello","idempotency_key":"imsg-test"}'
    timestamp = str(int(time.time()))
    return body, timestamp
