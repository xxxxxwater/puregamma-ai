from datetime import datetime, timezone
from decimal import Decimal
from functools import lru_cache
import holidays

@lru_cache(maxsize=8)
def china_days_off(year):
    return holidays.country_holidays("CN", years=[year])

def deepseek_peak(at=None):
    now = at or datetime.now(timezone.utc)
    return now.weekday() < 5 and (1 <= now.hour < 4 or 6 <= now.hour < 10) and now.date() not in china_days_off(now.year)

def effective_prices(revision, *, retail, maximum=False, peak=None):
    prices = revision.final_prices_json if retail else revision.official_prices_json
    if revision.source_reference != "https://api-docs.deepseek.com/quick_start/pricing/":
        return prices
    if not (maximum or (deepseek_peak() if peak is None else peak)):
        return prices
    return {key: {**item, "usd": str(Decimal(item["usd"]) * 2)} for key, item in prices.items()}
