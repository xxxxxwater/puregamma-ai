from __future__ import annotations

from packages.database.models import User


SUPPORTED_LOCALES = {"en", "zh"}
DEFAULT_LOCALE = "en"


def normalize_locale(value: str | None) -> str:
    return value if value in SUPPORTED_LOCALES else DEFAULT_LOCALE


def resolve_locale(
    *,
    query_locale: str | None = None,
    header_locale: str | None = None,
    user: User | None = None,
    cookie_locale: str | None = None,
) -> str:
    if query_locale:
        return normalize_locale(query_locale)
    if header_locale:
        return normalize_locale(header_locale)
    preference_locale = getattr(getattr(user, "preference", None), "locale", None)
    if preference_locale:
        return normalize_locale(preference_locale)
    if cookie_locale:
        return normalize_locale(cookie_locale)
    return DEFAULT_LOCALE
