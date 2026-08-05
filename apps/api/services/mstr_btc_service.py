"""MSTR/BTC opportunity dashboard: real-data pipeline for /opportunities/mstr-btc.

Data sources (all public, no credentials, no scraping in the browser):
  - https://api.strategy.com/btc/bitcoinKpis   live BTC price, mNAV, per-share economics
  - https://api.strategy.com/btc/mstrKpiData   live MSTR quote, market cap, EV, returns
  - https://api.strategy.com/btc/mstrOptionsData  live MSTR options IV/OI
  - https://www.strategy.com/ (__NEXT_DATA__)  official treasury tracker
    (BTC holdings, debt, preferred, USD reserve, share breakdown, BTC yield/gain,
    official metric definitions) updated with each 8-K, typically weekly.

Rules honored here:
  - LLM is never used to invent numbers. All metrics come from the sources above
    or from deterministic arithmetic whose methodology is attached to the metric.
  - When a source fails, dependent metrics degrade to status="unavailable" with a
    reason; the response never fabricates values.
  - Responses are cached in Redis; a last-good copy protects against transient
    source outages and is labeled status="delayed".
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any

import requests

from apps.api.config import get_settings

logger = logging.getLogger(__name__)

PAGE_URL = "https://www.strategy.com/"
BITCOIN_KPIS_URL = "https://api.strategy.com/btc/bitcoinKpis"
MSTR_KPI_URL = "https://api.strategy.com/btc/mstrKpiData"
OPTIONS_URL = "https://api.strategy.com/btc/mstrOptionsData"

USER_AGENT = "PureGamma-Research/1.0 (+https://puregamma.ai)"
# The JSON KPI APIs accept any UA, but www.strategy.com sits behind Cloudflare
# and 403s non-browser agents; the public page must be fetched with a browser UA.
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)

CACHE_KEY = "pg:opp:mstrbtc:factpack:v1"
LASTGOOD_KEY = "pg:opp:mstrbtc:lastgood:v1"
SERIES_KEY = "pg:opp:mstrbtc:series:v2"
TREASURY_SERIES_KEY = "pg:opp:mstrbtc:treasury-series:v1"
LOCK_KEY = "pg:opp:mstrbtc:lock"
CACHE_TTL_SECONDS = 120
LASTGOOD_TTL_SECONDS = 7 * 24 * 3600
SERIES_MAX_POINTS = 4000
SERIES_MIN_INTERVAL_SECONDS = 900  # 15 minutes between stored points
LIVE_MAX_AGE_SECONDS = 1800  # market data older than 30 min renders as delayed


# ---------------------------------------------------------------------------
# Fetch layer
# ---------------------------------------------------------------------------

def _http_get_json(url: str, *, max_bytes: int | None = None) -> Any:
    settings = get_settings()
    limit = max_bytes or settings.provider_max_response_bytes
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html"},
        timeout=settings.provider_http_timeout_seconds,
        stream=True,
    )
    response.raise_for_status()
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=65536):
        total += len(chunk)
        if total > limit:
            raise RuntimeError(f"response too large (> {limit} bytes)")
        chunks.append(chunk)
    body = b"".join(chunks)
    return json.loads(body.decode("utf-8", errors="replace"))


def _fetch_tracker_page() -> dict[str, Any]:
    """Extract btcTrackerData + official metric tooltips from __NEXT_DATA__."""
    settings = get_settings()
    response = requests.get(
        PAGE_URL,
        headers={"User-Agent": BROWSER_USER_AGENT, "Accept": "text/html"},
        timeout=settings.provider_http_timeout_seconds,
    )
    response.raise_for_status()
    if len(response.content) > settings.provider_max_response_bytes:
        raise RuntimeError("strategy.com page too large")
    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        response.text,
        re.S,
    )
    if not match:
        raise RuntimeError("__NEXT_DATA__ not found on strategy.com")
    data = json.loads(match.group(1))
    page_props = data.get("props", {}).get("pageProps", {})
    tracker_entries = page_props.get("btcTrackerData") or []
    if not tracker_entries:
        raise RuntimeError("btcTrackerData missing on strategy.com")
    ordered = sorted(
        tracker_entries,
        key=lambda entry: str(entry.get("as_of_date") or ""),
        reverse=True,
    )
    tooltips = {
        str(item.get("name")): str(item.get("tooltip"))
        for item in (page_props.get("tooltipData", {}) or {}).get("metric", [])
        if isinstance(item, dict) and item.get("name")
    }
    return {"latest": ordered[0], "previous": ordered[1] if len(ordered) > 1 else None, "tooltips": tooltips}


def fetch_fact_pack() -> dict[str, Any]:
    """Fetch all sources; a source failure is recorded, never fatal to others."""
    fetched_at = datetime.now(timezone.utc)
    errors: list[str] = []
    pack: dict[str, Any] = {"fetched_at": fetched_at.isoformat(), "errors": errors}

    try:
        kpis = _http_get_json(BITCOIN_KPIS_URL)
        pack["kpis"] = kpis.get("results") or {}
        pack["kpis_timestamp"] = kpis.get("timestamp")
    except Exception as exc:  # noqa: BLE001 - recorded, not raised
        logger.warning("mstr-btc: bitcoinKpis fetch failed: %s", exc)
        errors.append(f"bitcoinKpis:{type(exc).__name__}")
        pack["kpis"] = None
        pack["kpis_timestamp"] = None

    try:
        mstr = _http_get_json(MSTR_KPI_URL)
        pack["mstr"] = mstr[0] if isinstance(mstr, list) and mstr else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("mstr-btc: mstrKpiData fetch failed: %s", exc)
        errors.append(f"mstrKpiData:{type(exc).__name__}")
        pack["mstr"] = None

    try:
        pack["options"] = _http_get_json(OPTIONS_URL)
    except Exception as exc:  # noqa: BLE001
        logger.warning("mstr-btc: mstrOptionsData fetch failed: %s", exc)
        errors.append(f"mstrOptionsData:{type(exc).__name__}")
        pack["options"] = None

    try:
        pack["tracker"] = _fetch_tracker_page()
    except Exception as exc:  # noqa: BLE001
        logger.warning("mstr-btc: strategy.com tracker fetch failed: %s", exc)
        errors.append(f"strategyTracker:{type(exc).__name__}")
        pack["tracker"] = None

    return pack


# ---------------------------------------------------------------------------
# Normalization helpers
# ---------------------------------------------------------------------------

def _num(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).replace(",", "").replace("%", "").strip()
    if not text or text in {"—", "-", "null", "None"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _iso_utc(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    try:
        dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _age_seconds(iso: str | None, now: datetime) -> float | None:
    if not iso:
        return None
    try:
        return (now - datetime.fromisoformat(iso)).total_seconds()
    except ValueError:
        return None


def _fmt_usd(value: float | None) -> str:
    if value is None:
        return ""
    if abs(value) >= 1_000_000_000:
        return f"${value / 1_000_000_000:,.2f}B"
    if abs(value) >= 1_000_000:
        return f"${value / 1_000_000:,.0f}M"
    return f"${value:,.2f}"


def _fmt_number(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:,.{digits}f}"


def _fmt_pct(value: float | None, digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:+.{digits}f}%" if value else "0.00%"


def _fmt_int(value: float | None) -> str:
    if value is None:
        return ""
    return f"{int(round(value)):,}"


# ---------------------------------------------------------------------------
# Labels / definitions (en + zh)
# ---------------------------------------------------------------------------

_LABELS: dict[str, dict[str, str]] = {
    "mstr_price": {"en": "MSTR price", "zh": "MSTR 价格"},
    "btc_price": {"en": "BTC price", "zh": "BTC 价格"},
    "market_cap": {"en": "Market cap", "zh": "市值"},
    "enterprise_value": {"en": "Enterprise value", "zh": "企业价值"},
    "mnav": {"en": "mNAV", "zh": "mNAV"},
    "premium_discount": {"en": "Premium / discount to NAV", "zh": "相对 NAV 溢价/折价"},
    "btc_nav": {"en": "BTC reserve value", "zh": "BTC 储备价值"},
    "total_btc_reserves": {"en": "BTC holdings", "zh": "BTC 持仓量"},
    "usd_reserve": {"en": "USD reserve", "zh": "美元储备"},
    "total_debt": {"en": "Total debt", "zh": "总债务"},
    "preferred_equity": {"en": "Preferred equity (notional)", "zh": "优先股（名义值）"},
    "net_btc_reserves": {"en": "Net BTC reserve", "zh": "净 BTC 储备"},
    "net_leverage": {"en": "Net leverage", "zh": "净杠杆"},
    "annual_interest_dividend": {"en": "Annual interest + dividends", "zh": "年度利息+股息"},
    "interest_dividend_coverage": {"en": "Coverage (BTC reserve years)", "zh": "覆盖倍数（BTC 储备年数）"},
    "btc_duration": {"en": "BTC duration (yrs)", "zh": "BTC 久期（年）"},
    "usd_duration": {"en": "USD duration (yrs)", "zh": "美元久期（年）"},
    "debt_maturity": {"en": "Avg debt maturity (yrs)", "zh": "平均债务期限（年）"},
    "btc_per_share": {"en": "BTC per share ($)", "zh": "每股 BTC（美元）"},
    "net_btc_per_share": {"en": "Net BTC per share ($)", "zh": "每股净 BTC（美元）"},
    "diluted_shares": {"en": "Fully diluted shares", "zh": "完全摊薄股数"},
    "btc_exposure_per_share": {"en": "BTC exposure per share (sats)", "zh": "每股 BTC 敞口（聪）"},
    "nav_per_share": {"en": "NAV per share ($)", "zh": "每股 NAV（美元）"},
    "per_share_economics_change": {"en": "Per-share economics 24h", "zh": "每股经济学 24h 变化"},
    "one_year_return": {"en": "1Y return", "zh": "1 年收益率"},
    "annualized_return": {"en": "BSE return (ann.)", "zh": "比特币标准时代年化"},
    "btc_yield": {"en": "BTC yield YTD", "zh": "BTC 收益率 YTD"},
    "btc_gain": {"en": "BTC gain YTD", "zh": "BTC 增益 YTD"},
    "btc_dollar_gain": {"en": "BTC gain YTD ($)", "zh": "BTC 增益 YTD（美元）"},
    "earnings": {"en": "Software earnings", "zh": "软件业务盈利"},
    "estimated_earnings_impact": {"en": "Est. earnings impact", "zh": "预估盈利影响"},
    "floor": {"en": "Balance-sheet floor / share", "zh": "资产负债表底线/股"},
    "breakeven": {"en": "BTC breakeven price", "zh": "BTC 盈亏平衡价"},
    "downside_buffer": {"en": "Downside buffer", "zh": "下行缓冲"},
    "price_hurdles": {"en": "MSTR price at mNAV=1", "zh": "mNAV=1 对应 MSTR 价格"},
    "mnav_hurdles": {"en": "BTC price at mNAV=1", "zh": "mNAV=1 对应 BTC 价格"},
    "btc_price_hurdles": {"en": "BTC hurdle rate (ann.)", "zh": "BTC 门槛收益率（年化）"},
    "implied_volatility": {"en": "Implied volatility", "zh": "隐含波动率"},
    "open_interest": {"en": "Options open interest", "zh": "期权未平仓"},
}

_DEFINITIONS_ZH: dict[str, str] = {
    "mstr_price": "MSTR 最新成交价。交易时段每 15 秒更新。",
    "btc_price": "BTC 最新美元价格。",
    "market_cap": "全部基本流通股的总市值。",
    "enterprise_value": "基本股市值 + 债务 + 优先股 − 美元储备。",
    "mnav": "MSTR 价格 ÷ 每股净 BTC（美元），衡量 MSTR 相对其扣除债务与优先股后的每股比特币价值的溢价/折价。",
    "premium_discount": "mNAV − 1，以百分比表示的相对净资产溢价或折价。",
    "btc_nav": "持仓 BTC 数量 × BTC 价格的市值。",
    "total_btc_reserves": "公司持有的比特币总量。随每份 8-K 文件更新，通常每周一次。",
    "usd_reserve": "用于支付优先股股息与债务利息的美元流动性储备，不同于资产负债表上的全部现金。",
    "total_debt": "未偿还债务本金总额。随每份 8-K 更新。",
    "preferred_equity": "未偿还永续优先股的名义总额（按当前汇率折算美元）。",
    "net_btc_reserves": "BTC 储备市值减去债务与优先股（加回美元储备）后的净额。",
    "net_leverage": "（债务 − 美元储备）÷ BTC 储备市值。",
    "annual_interest_dividend": "优先股股息与债务利息的年度化义务。",
    "interest_dividend_coverage": "BTC 储备市值 ÷ 年度利息+股息，以年数表示。",
    "btc_duration": "BTC 储备 ÷ 年度利息+股息（年）。",
    "usd_duration": "美元储备 ÷ 年度利息+股息（年）。",
    "debt_maturity": "未偿还债务的平均期限（年）。",
    "btc_per_share": "每股对应的 BTC 美元价值（毛口径）。",
    "net_btc_per_share": "扣除债务与优先股后每股对应的 BTC 美元价值。",
    "diluted_shares": "基本流通股 + 可转债转换股 + 期权 + 未归属 RSU/PSU。",
    "btc_exposure_per_share": "每股对应的比特币数量（聪）。",
    "nav_per_share": "每股净资产价值（扣除债务与优先股）。",
    "per_share_economics_change": "每股净 BTC 美元价值的 24 小时变化。",
    "one_year_return": "MSTR 过去 12 个月收益率。",
    "annualized_return": "自比特币标准时代（2020-08-10）以来的 MSTR 年化收益率。",
    "btc_yield": "年初至今每股 BTC 含量的增长率（公司官方口径）。",
    "btc_gain": "年初至今 BTC 含量增长对应的比特币数量。",
    "btc_dollar_gain": "BTC 增益 × 当前 BTC 价格（美元口径估算）。",
    "earnings": "软件业务盈利数据。",
    "estimated_earnings_impact": "对盈利的预估影响。",
    "floor": "（债务 + 优先股 − 美元储备）÷ 完全摊薄股数：BTC 价值归零时每股的净负债。",
    "breakeven": "使 BTC 储备市值等于净负债（债务+优先股−美元储备）的 BTC 价格。",
    "downside_buffer": "当前 BTC 价格相对盈亏平衡价的缓冲百分比。",
    "price_hurdles": "使 mNAV 等于 1 的 MSTR 价格（即每股净 BTC 美元价值）。",
    "mnav_hurdles": "在当前 MSTR 价格下使 mNAV 等于 1 的 BTC 价格。",
    "btc_price_hurdles": "覆盖年度资本成本所需的 BTC 年化涨幅（来源口径）。",
    "implied_volatility": "市场对 MSTR 期权存续期内波动率的预期。",
    "open_interest": "MSTR 期权未平仓合约名义总额。",
}

_METHODOLOGY: dict[str, dict[str, str]] = {
    "premium_discount": {"en": "(mNAV − 1) × 100, from source mNAV.", "zh": "（mNAV − 1）× 100，取自数据源 mNAV。"},
    "diluted_shares": {"en": "Basic shares + convert shares (2028/2029/2030A/2030B/2031/2032/STRK) + options + unvested RSU/PSU, per official tracker.", "zh": "基本股 + 可转债转换股（2028/2029/2030A/2030B/2031/2032/STRK）+ 期权 + 未归属 RSU/PSU，取自官方追踪页。"},
    "floor": {"en": "(Debt + Preferred − USD reserve) / fully diluted shares.", "zh": "（债务 + 优先股 − 美元储备）÷ 完全摊薄股数。"},
    "breakeven": {"en": "(Debt + Preferred − USD reserve) / BTC holdings.", "zh": "（债务 + 优先股 − 美元储备）÷ BTC 持仓量。"},
    "downside_buffer": {"en": "1 − breakeven / current BTC price.", "zh": "1 − 盈亏平衡价 ÷ 当前 BTC 价格。"},
    "mnav_hurdles": {"en": "(MSTR price × diluted shares + net claims) / BTC holdings.", "zh": "（MSTR 价格 × 摊薄股数 + 净负债）÷ BTC 持仓量。"},
    "net_leverage": {"en": "(Debt − USD reserve) / BTC reserve value.", "zh": "（债务 − 美元储备）÷ BTC 储备市值。"},
    "btc_dollar_gain": {"en": "BTC gain YTD × current BTC price.", "zh": "BTC 增益 YTD × 当前 BTC 价格。"},
    "nav_per_share": {"en": "Net BTC per share ($) from source (net of debt and preferred claims).", "zh": "数据源每股净 BTC 美元价值（已扣除债务与优先股）。"},
}


def _text(table: dict[str, dict[str, str]], key: str, locale: str) -> str:
    entry = table.get(key) or {}
    return entry.get("zh" if locale == "zh" else "en") or entry.get("en") or ""


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

_DEFINITIONS_EN: dict[str, str] = {
    "btc_price": "The latest BTC/USD price.",
    "premium_discount": "mNAV − 1 expressed as a percentage premium or discount to net asset value.",
    "btc_nav": "Market value of BTC holdings: BTC count × BTC price.",
    "net_btc_reserves": "BTC reserve value net of debt and preferred claims (plus USD reserve).",
    "net_leverage": "(Debt − USD reserve) / BTC reserve value.",
    "interest_dividend_coverage": "BTC reserve value / annual interest+dividends, in years.",
    "btc_per_share": "USD value of BTC per share (gross).",
    "net_btc_per_share": "USD value of BTC per share net of debt and preferred claims.",
    "diluted_shares": "Basic shares + convert shares + options + unvested RSU/PSU.",
    "btc_exposure_per_share": "BTC per share denominated in satoshis.",
    "nav_per_share": "Net asset value per share (net of debt and preferred claims).",
    "per_share_economics_change": "24h change in net BTC per share ($).",
    "floor": "(Debt + Preferred − USD reserve) / fully diluted shares: per-share net claims if BTC were worthless.",
    "breakeven": "BTC price at which the BTC reserve value equals net claims (debt + preferred − USD reserve).",
    "downside_buffer": "Percentage buffer of the current BTC price above the breakeven price.",
    "price_hurdles": "MSTR price at which mNAV equals 1 (i.e. net BTC per share in USD).",
    "mnav_hurdles": "BTC price at which mNAV equals 1 given the current MSTR price.",
    "btc_price_hurdles": "Annualized BTC appreciation required to cover annual capital costs (source caliber).",
    "implied_volatility": "Market expectation of MSTR volatility over the life of its options.",
    "open_interest": "Notional open interest across MSTR options.",
    "earnings": "Software-segment earnings.",
    "estimated_earnings_impact": "Estimated impact on earnings.",
}


def _metric(
    metric_id: str,
    value: float | str | None,
    formatted: str,
    *,
    locale: str,
    as_of: str | None,
    source_url: str,
    status: str,
    unit: str | None = None,
    change_24h: float | None = None,
    tooltips: dict[str, str] | None = None,
    tooltip_name: str | None = None,
    unavailable_reason: str | None = None,
) -> dict[str, Any]:
    if locale == "zh":
        definition = _DEFINITIONS_ZH.get(metric_id, "")
    else:
        definition = ""
        if tooltips and tooltip_name:
            definition = tooltips.get(tooltip_name) or ""
        if not definition:
            definition = _DEFINITIONS_EN.get(metric_id, "")
    return {
        "id": metric_id,
        "label": _text(_LABELS, metric_id, locale),
        "value": value,
        "formattedValue": formatted,
        "unit": unit,
        "change24h": change_24h,
        "asOf": as_of,
        "sourceUrl": source_url,
        "definition": definition or None,
        "methodology": _text(_METHODOLOGY, metric_id, locale) or None,
        "status": status,
        "unavailableReason": unavailable_reason,
    }


def _unavailable(metric_id: str, *, locale: str, reason: str) -> dict[str, Any]:
    return _metric(
        metric_id,
        None,
        "",
        locale=locale,
        as_of=None,
        source_url=PAGE_URL,
        status="unavailable",
        unavailable_reason=reason,
    )


def build_dashboard(pack: dict[str, Any], locale: str, *, series: dict[str, list] | None = None, served_from: str = "live") -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    kpis = pack.get("kpis") or {}
    mstr = pack.get("mstr") or {}
    tracker = (pack.get("tracker") or {}).get("latest") or {}
    previous = (pack.get("tracker") or {}).get("previous") or {}
    tooltips = (pack.get("tracker") or {}).get("tooltips") or {}
    options = pack.get("options") or {}
    errors: list[str] = list(pack.get("errors") or [])

    kpis_as_of = _iso_utc(pack.get("kpis_timestamp") or kpis.get("timestamp") or mstr.get("timeStampUtc"))
    mstr_as_of = _iso_utc(mstr.get("timeStampUtc")) or kpis_as_of
    tracker_as_of = None
    if tracker.get("as_of_date"):
        tracker_as_of = f"{tracker['as_of_date']}T00:00:00+00:00"
    fetched_at = pack.get("fetched_at")

    kpis_age = _age_seconds(kpis_as_of, now)
    market_status = "unavailable"
    if kpis or mstr:
        market_status = "live" if (kpis_age is not None and kpis_age <= LIVE_MAX_AGE_SECONDS) else "delayed"
    if served_from in {"cache", "last_good"} and market_status == "live":
        market_status = "delayed"
    tracker_status = "live" if tracker else "unavailable"

    # ---- raw values -------------------------------------------------------
    btc_price = _num(kpis.get("ufPrice") or kpis.get("latestPrice"))
    btc_change = _num(kpis.get("priceVarPerc"))
    mstr_price = _num(mstr.get("ufPrice"))
    mstr_change = _num(mstr.get("priceVarPerc"))
    market_cap_m = _num(mstr.get("marketCap"))
    ent_val_m = _num(mstr.get("entVal"))
    debt_m = _num(mstr.get("debt"))
    pref_m = _num(mstr.get("pref"))
    mnav = _num(kpis.get("mNav"))
    btc_nav_m = _num(kpis.get("btcNavNumber"))
    net_btc_reserve = _num(kpis.get("netBtcReserve"))
    net_btc_per_share = _num(kpis.get("netBtcPerShareUsd"))
    btc_per_share = _num(kpis.get("btcPerShareUsd"))
    sats_per_share = _num(kpis.get("satsPerShare"))
    net_sats_per_share = _num(kpis.get("netSatsPerShare"))
    annual_dividends = _num(kpis.get("totalAnnualDividends"))
    btc_years = _num(kpis.get("btcYearsOfDividends"))
    usd_months = _num(kpis.get("usdMonthsOfDividends"))
    one_year = _num(mstr.get("oneYear"))
    bse_annualized = _num(mstr.get("bseAnnualized"))
    amplification = _num(kpis.get("amplification"))
    total_duration = _num(kpis.get("totalDuration"))
    bitcoin_hurdle = _num(kpis.get("bitcoinHurdleArr"))
    iv = _num(options.get("impliedVolatility"))
    total_oi = _num(options.get("totalOi"))
    per_share_change = _num(kpis.get("netBtcPerShareUsdVarPerc"))

    holdings = _num(tracker.get("btc_holdings"))
    debt = _num(tracker.get("debt"))
    pref = _num(tracker.get("pref"))
    cash = _num(tracker.get("cash"))
    basic_shares = _num(tracker.get("basic_shares_outstanding"))
    shares_breakdown = tracker.get("shares") or {}
    dilution_parts = {k: _num(v) or 0.0 for k, v in shares_breakdown.items()}
    diluted_shares = (basic_shares or 0) + sum(dilution_parts.values()) if basic_shares else None
    debt_years = _num(tracker.get("debt_years"))
    btc_yield_ytd = _num(tracker.get("btc_yield_ytd"))
    btc_gain_ytd = _num(tracker.get("btc_gain_ytd"))

    # derived claims
    net_claims = None
    if debt is not None and pref is not None:
        net_claims = debt + pref - (cash or 0)
    floor_per_share = (net_claims / diluted_shares) if (net_claims is not None and diluted_shares) else None
    breakeven_btc = (net_claims / holdings) if (net_claims is not None and holdings) else None
    downside_buffer = (1 - breakeven_btc / btc_price) * 100 if (breakeven_btc and btc_price) else None
    btc_price_for_parity = None
    if mstr_price and diluted_shares and holdings and net_claims is not None:
        btc_price_for_parity = (mstr_price * diluted_shares + net_claims) / holdings
    net_leverage = None
    if debt is not None and btc_nav_m:
        net_leverage = (debt - (cash or 0)) / (btc_nav_m * 1_000_000)
    btc_dollar_gain = (btc_gain_ytd * btc_price) if (btc_gain_ytd is not None and btc_price) else None

    market_src = BITCOIN_KPIS_URL
    metrics: list[dict[str, Any]] = []

    def add(metric_id: str, value: float | str | None, formatted: str, *, as_of: str | None, source: str, status: str, unit: str | None = None, change: float | None = None, tooltip: str | None = None, reason: str | None = None) -> None:
        metrics.append(_metric(metric_id, value, formatted, locale=locale, as_of=as_of, source_url=source, status=status, unit=unit, change_24h=change, tooltips=tooltips, tooltip_name=tooltip, unavailable_reason=reason))

    if market_status == "unavailable":
        for mid in ("mstr_price", "btc_price", "market_cap", "enterprise_value", "mnav", "premium_discount", "btc_nav", "net_btc_reserves", "net_leverage", "annual_interest_dividend", "interest_dividend_coverage", "btc_duration", "usd_duration", "btc_per_share", "net_btc_per_share", "btc_exposure_per_share", "nav_per_share", "per_share_economics_change", "one_year_return", "annualized_return", "implied_volatility", "open_interest", "btc_price_hurdles"):
            add(mid, None, "", as_of=None, source=market_src, status="unavailable", reason="source_unavailable:strategy_kpi_api")
    else:
        add("mstr_price", mstr_price, _fmt_usd(mstr_price), as_of=mstr_as_of, source=MSTR_KPI_URL, status=market_status, change=mstr_change, tooltip="MSTR Price")
        add("btc_price", btc_price, _fmt_usd(btc_price), as_of=kpis_as_of, source=market_src, status=market_status, change=btc_change, tooltip="BTC")
        add("market_cap", (market_cap_m or 0) * 1_000_000 if market_cap_m else None, _fmt_usd(market_cap_m * 1_000_000 if market_cap_m else None), as_of=mstr_as_of, source=MSTR_KPI_URL, status=market_status, change=_num(mstr.get("marketCapVarPerc")), tooltip="Market Cap ($M)")
        add("enterprise_value", ent_val_m * 1_000_000 if ent_val_m else None, _fmt_usd(ent_val_m * 1_000_000 if ent_val_m else None), as_of=mstr_as_of, source=MSTR_KPI_URL, status=market_status, change=_num(mstr.get("entValPerc")), tooltip="Enterprise Value ($M)")
        add("mnav", mnav, _fmt_number(mnav, 4), as_of=kpis_as_of, source=market_src, status=market_status, change=_num(kpis.get("mNavVarPerc")), tooltip="mNAV")
        add("premium_discount", (mnav - 1) * 100 if mnav is not None else None, _fmt_pct((mnav - 1) * 100 if mnav is not None else None), as_of=kpis_as_of, source=market_src, status=market_status, tooltip="mNAV")
        add("btc_nav", btc_nav_m * 1_000_000 if btc_nav_m else None, _fmt_usd(btc_nav_m * 1_000_000 if btc_nav_m else None), as_of=kpis_as_of, source=market_src, status=market_status, tooltip="BTC Reserve ($M)")
        add("net_btc_reserves", net_btc_reserve, _fmt_usd(net_btc_reserve), as_of=kpis_as_of, source=market_src, status=market_status, tooltip="Total Reserve ($M)")
        add("net_leverage", net_leverage, _fmt_number(net_leverage, 3), as_of=kpis_as_of, source=market_src, status=market_status, tooltip="Net Leverage")
        add("annual_interest_dividend", annual_dividends, _fmt_usd(annual_dividends), as_of=kpis_as_of, source=market_src, status=market_status, tooltip="Annual Int + Div ($M)")
        add("interest_dividend_coverage", btc_years, _fmt_number(btc_years, 1), as_of=kpis_as_of, source=market_src, status=market_status, unit="yrs", tooltip="BTC Duration (Yrs)")
        add("btc_duration", btc_years, _fmt_number(btc_years, 1), as_of=kpis_as_of, source=market_src, status=market_status, unit="yrs", tooltip="BTC Duration (Yrs)")
        add("usd_duration", (usd_months / 12) if usd_months else None, _fmt_number((usd_months / 12) if usd_months else None, 1), as_of=kpis_as_of, source=market_src, status=market_status, unit="yrs", tooltip="USD Duration (Yrs)")
        add("btc_per_share", btc_per_share, _fmt_usd(btc_per_share), as_of=kpis_as_of, source=market_src, status=market_status, change=_num(kpis.get("btcPerShareUsdVarPerc")))
        add("net_btc_per_share", net_btc_per_share, _fmt_usd(net_btc_per_share), as_of=kpis_as_of, source=market_src, status=market_status, change=per_share_change)
        add("btc_exposure_per_share", sats_per_share, _fmt_int(sats_per_share), as_of=kpis_as_of, source=market_src, status=market_status, unit="sats")
        add("nav_per_share", net_btc_per_share, _fmt_usd(net_btc_per_share), as_of=kpis_as_of, source=market_src, status=market_status)
        add("per_share_economics_change", per_share_change, _fmt_pct(per_share_change), as_of=kpis_as_of, source=market_src, status=market_status)
        add("one_year_return", one_year, _fmt_pct(one_year, 0), as_of=mstr_as_of, source=MSTR_KPI_URL, status=market_status, tooltip="1Y Return")
        add("annualized_return", bse_annualized, _fmt_pct(bse_annualized, 0), as_of=mstr_as_of, source=MSTR_KPI_URL, status=market_status, tooltip="BSE Return (Ann.)")
        add("implied_volatility", iv, _fmt_number(iv, 0) if iv is not None else "", as_of=kpis_as_of, source=OPTIONS_URL, status=market_status if iv is not None else "unavailable", unit="%", tooltip="Implied Volatility", reason=None if iv is not None else "field_missing:mstrOptionsData.impliedVolatility")
        add("open_interest", (total_oi or 0) * 1_000_000 if total_oi else None, _fmt_usd(total_oi * 1_000_000 if total_oi else None), as_of=kpis_as_of, source=OPTIONS_URL, status=market_status if total_oi else "unavailable", tooltip="Open Interest ($M)", reason=None if total_oi else "field_missing:mstrOptionsData.totalOi")
        add("btc_price_hurdles", bitcoin_hurdle, _fmt_pct(bitcoin_hurdle), as_of=kpis_as_of, source=market_src, status=market_status if bitcoin_hurdle is not None else "unavailable", reason=None if bitcoin_hurdle is not None else "field_missing:bitcoinKpis.bitcoinHurdleArr")

    # treasury metrics
    if tracker_status == "unavailable":
        for mid in ("total_btc_reserves", "usd_reserve", "total_debt", "preferred_equity", "diluted_shares", "debt_maturity", "btc_yield", "btc_gain", "floor", "breakeven", "downside_buffer", "price_hurdles", "mnav_hurdles", "btc_dollar_gain"):
            add(mid, None, "", as_of=None, source=PAGE_URL, status="unavailable", reason="source_unavailable:strategy_tracker_page")
    else:
        add("total_btc_reserves", holdings, f"{_fmt_int(holdings)} BTC", as_of=tracker_as_of, source=PAGE_URL, status="delayed" if market_status == "delayed" else "live", tooltip="BTC")
        add("usd_reserve", cash, _fmt_usd(cash), as_of=tracker_as_of, source=PAGE_URL, status="live", tooltip="USD Reserve ($M)")
        add("total_debt", debt, _fmt_usd(debt), as_of=tracker_as_of, source=PAGE_URL, status="live", tooltip="Debt ($M)")
        add("preferred_equity", pref, _fmt_usd(pref), as_of=tracker_as_of, source=PAGE_URL, status="live", tooltip="Pref ($M)")
        add("diluted_shares", diluted_shares, _fmt_int(diluted_shares), as_of=tracker_as_of, source=PAGE_URL, status="live")
        add("debt_maturity", debt_years, _fmt_number(debt_years, 1), as_of=tracker_as_of, source=PAGE_URL, status="live", unit="yrs")
        add("btc_yield", btc_yield_ytd, _fmt_pct(btc_yield_ytd), as_of=tracker_as_of, source=PAGE_URL, status="live")
        add("btc_gain", btc_gain_ytd, f"{_fmt_int(btc_gain_ytd)} BTC", as_of=tracker_as_of, source=PAGE_URL, status="live")
        add("btc_dollar_gain", btc_dollar_gain, _fmt_usd(btc_dollar_gain), as_of=kpis_as_of or tracker_as_of, source=PAGE_URL, status=market_status)
        if floor_per_share is not None:
            add("floor", floor_per_share, _fmt_usd(floor_per_share), as_of=tracker_as_of, source=PAGE_URL, status="live")
        else:
            add("floor", None, "", as_of=None, source=PAGE_URL, status="unavailable", reason="missing_inputs:claims_or_shares")
        if breakeven_btc is not None:
            add("breakeven", breakeven_btc, _fmt_usd(breakeven_btc), as_of=tracker_as_of, source=PAGE_URL, status="live")
        else:
            add("breakeven", None, "", as_of=None, source=PAGE_URL, status="unavailable", reason="missing_inputs:claims_or_holdings")
        if downside_buffer is not None:
            add("downside_buffer", downside_buffer, _fmt_pct(downside_buffer), as_of=kpis_as_of, source=PAGE_URL, status=market_status)
        else:
            add("downside_buffer", None, "", as_of=None, source=PAGE_URL, status="unavailable", reason="missing_inputs:btc_price")
        add("price_hurdles", net_btc_per_share, _fmt_usd(net_btc_per_share), as_of=kpis_as_of, source=market_src, status=market_status)
        add("mnav_hurdles", btc_price_for_parity, _fmt_usd(btc_price_for_parity), as_of=kpis_as_of, source=market_src, status=market_status if btc_price_for_parity else "unavailable", reason=None if btc_price_for_parity else "missing_inputs:mstr_price_or_shares")

    # earnings metrics: no confirmed public source -> explicitly unavailable
    earnings_reason = "no_confirmed_source" if locale != "zh" else "无已确认数据源"
    add("earnings", None, "", as_of=None, source=PAGE_URL, status="unavailable", reason=earnings_reason)
    add("estimated_earnings_impact", None, "", as_of=None, source=PAGE_URL, status="unavailable", reason=earnings_reason)

    # ---- scenarios ---------------------------------------------------------
    scenarios: list[dict[str, Any]] = []
    scenario_status = market_status if tracker_status != "unavailable" and market_status != "unavailable" else "unavailable"
    if scenario_status != "unavailable":
        scenarios.append({
            "id": "mnav_parity",
            "name": "mNAV = 1 parity" if locale != "zh" else "mNAV = 1 平价",
            "description": ("BTC and MSTR prices at which MSTR trades exactly at net BTC value per share." if locale != "zh" else "使 MSTR 恰好按每股净 BTC 价值成交的 BTC 与 MSTR 价格。"),
            "asOf": kpis_as_of,
            "status": scenario_status,
            "sourceUrl": BITCOIN_KPIS_URL,
            "assumptions": {"diluted_shares": diluted_shares, "net_claims_usd": net_claims, "btc_holdings": holdings},
            "outputs": {"mstr_price_at_parity": net_btc_per_share, "btc_price_at_parity": btc_price_for_parity, "current_mnav": mnav},
        })
        scenarios.append({
            "id": "balance_sheet_floor",
            "name": "Balance-sheet floor" if locale != "zh" else "资产负债表底线",
            "description": ("Per-share net claims if BTC were worthless, and the BTC price at which reserves equal net claims." if locale != "zh" else "BTC 价值归零时每股净负债，以及储备等于净负债的 BTC 价格。"),
            "asOf": tracker_as_of,
            "status": scenario_status,
            "sourceUrl": PAGE_URL,
            "assumptions": {"debt_usd": debt, "preferred_usd": pref, "usd_reserve": cash, "btc_holdings": holdings},
            "outputs": {"floor_per_share": floor_per_share, "btc_breakeven_price": breakeven_btc, "downside_buffer_pct": downside_buffer},
        })
        scenarios.append({
            "id": "dilution_schedule",
            "name": "Dilution schedule" if locale != "zh" else "摊薄时间表",
            "description": ("Basic vs fully diluted share count using the official convert/option/RSU breakdown." if locale != "zh" else "基于官方可转债/期权/RSU 明细的基本股与完全摊薄股数对比。"),
            "asOf": tracker_as_of,
            "status": scenario_status,
            "sourceUrl": PAGE_URL,
            "assumptions": {k: v for k, v in dilution_parts.items()},
            "outputs": {"basic_shares": basic_shares, "fully_diluted_shares": diluted_shares, "dilution_pct": ((diluted_shares - basic_shares) / basic_shares * 100) if basic_shares and diluted_shares else None},
        })
        scenarios.append({
            "id": "coverage_stress",
            "name": "Coverage stress" if locale != "zh" else "覆盖压力测试",
            "description": ("Years of annual interest+dividends covered by BTC reserve and months covered by USD reserve at current values." if locale != "zh" else "按当前价值，BTC 储备可覆盖年度利息+股息的年数与美元储备可覆盖的月数。"),
            "asOf": kpis_as_of,
            "status": scenario_status,
            "sourceUrl": BITCOIN_KPIS_URL,
            "assumptions": {"annual_obligation_usd": annual_dividends, "btc_nav_usd": (btc_nav_m or 0) * 1_000_000 if btc_nav_m else None, "usd_reserve": cash},
            "outputs": {"btc_years_of_coverage": btc_years, "usd_months_of_coverage": usd_months, "amplification": amplification, "total_duration_years": total_duration},
        })

    # ---- research layer (deterministic; numbers only from sources) ---------
    research = _build_research(
        locale=locale,
        market_status=market_status,
        tracker_status=tracker_status,
        kpis_as_of=kpis_as_of,
        mnav=mnav,
        net_leverage=net_leverage,
        btc_years=btc_years,
        one_year=one_year,
        drawdown_from_ath=_num(kpis.get("drawdownFromAth")),
        annual_dividends=annual_dividends,
        downside_buffer=downside_buffer,
        btc_yield_ytd=btc_yield_ytd,
        tracker_title=tracker.get("title"),
        tracker_as_of=tracker.get("as_of_date"),
        previous_as_of=previous.get("as_of_date"),
        errors=errors,
    )

    # ---- notes --------------------------------------------------------------
    notes: list[str] = []
    if locale == "zh":
        notes.append("价格类指标由 api.strategy.com 提供，交易时段约每 15 秒更新；页面渲染前可能最多缓存 2 分钟。")
        notes.append("持仓、债务、优先股与美元储备来自 strategy.com 官方追踪页，随每份 8-K 更新（通常每周）。")
        notes.append(f"最近两期追踪快照：{tracker.get('as_of_date') or '—'} 与 {previous.get('as_of_date') or '—'}。")
        notes.append("软件业务盈利与盈利影响暂无已确认数据源，相关指标标记为不可用，不做估算。")
    else:
        notes.append("Price metrics are served by api.strategy.com (~15s cadence during market hours); this response may be cached up to 2 minutes.")
        notes.append("Holdings, debt, preferred and USD reserve come from the official strategy.com tracker, updated with each 8-K (typically weekly).")
        notes.append(f"Latest tracker snapshots: {tracker.get('as_of_date') or '—'} and {previous.get('as_of_date') or '—'}.")
        notes.append("Software earnings and earnings-impact figures have no confirmed source and are reported as unavailable rather than estimated.")
    if errors:
        notes.append(("Degraded sources: " if locale != "zh" else "降级数据源：") + ", ".join(errors))

    source_status = "live"
    # Metrics that are intentionally unavailable (no confirmed source) must not
    # downgrade the whole dashboard.
    intentionally_unavailable = {"earnings", "estimated_earnings_impact"}
    statuses = {m["status"] for m in metrics if m["id"] not in intentionally_unavailable}
    if market_status == "unavailable" and tracker_status == "unavailable":
        source_status = "unavailable"
    elif "unavailable" in statuses or market_status == "delayed" or served_from != "live":
        source_status = "delayed" if (market_status != "unavailable" or tracker_status != "unavailable") else "unavailable"

    return {
        "asOf": kpis_as_of or tracker_as_of or fetched_at,
        "sourceStatus": source_status,
        "sourceUrl": PAGE_URL,
        "metrics": metrics,
        "series": series or {},
        "scenarios": scenarios,
        "research": research,
        "notes": notes,
    }


def _build_research(
    *,
    locale: str,
    market_status: str,
    tracker_status: str,
    kpis_as_of: str | None,
    mnav: float | None,
    net_leverage: float | None,
    btc_years: float | None,
    one_year: float | None,
    drawdown_from_ath: float | None,
    annual_dividends: float | None,
    downside_buffer: float | None,
    btc_yield_ytd: float | None,
    tracker_title: str | None,
    tracker_as_of: str | None,
    previous_as_of: str | None,
    errors: list[str],
) -> dict[str, Any] | None:
    if market_status == "unavailable" and tracker_status == "unavailable":
        return None

    gaps: list[str] = []
    if market_status == "unavailable":
        gaps.append("Live KPI API unreachable; price-derived analysis degraded." if locale != "zh" else "实时 KPI 接口不可达，价格相关分析降级。")
    if tracker_status == "unavailable":
        gaps.append("Official treasury tracker unreachable; balance-sheet analysis degraded." if locale != "zh" else "官方持仓追踪页不可达，资产负债表分析降级。")
    gaps.append("Software-segment earnings are not published in this feed." if locale != "zh" else "该数据链路未包含软件业务盈利数据。")
    for err in errors:
        gaps.append(err)

    def fmt(v: float | None, f=_fmt_number) -> str:
        return f(v) if v is not None else ("待确认" if locale == "zh" else "unconfirmed")

    if locale == "zh":
        conclusion = (
            f"MSTR 当前 mNAV 为 {fmt(mnav, lambda x: _fmt_number(x, 3))}，"
            f"相对每股净 BTC 价值{'溢价' if (mnav or 1) >= 1 else '折价'} {fmt(abs((mnav or 1) - 1) * 100 if mnav is not None else None)}%；"
            f"净杠杆 {fmt(net_leverage, lambda x: _fmt_number(x, 3))}，"
            f"BTC 储备可覆盖年度利息与股息 {fmt(btc_years, lambda x: _fmt_number(x, 1))} 年。"
        )
        bull = f"BTC 收益率 YTD {fmt(btc_yield_ytd)}%，持仓规模继续增长；若 mNAV 维持溢价，公司可继续以溢价融资增持 BTC，每股 BTC 含量复利上升。"
        base = f"价格与 mNAV 围绕净资产波动；年度资本义务约 {_fmt_usd(annual_dividends)}，按当前储备覆盖充足，BTC 一年收益 {fmt(one_year, lambda x: _fmt_pct(x, 0))}。"
        bear = f"若 mNAV 转折价且 BTC 下跌（当前距历史高点 {fmt(drawdown_from_ath, lambda x: _fmt_pct(x, 1))}），溢价融资链条收紧，每股增益放缓，下行缓冲约 {fmt(downside_buffer, lambda x: _fmt_pct(x, 1))}。"
        hurdle = "最大不确定性：软件业务盈利未在本数据链中披露，偿债义务完全依赖资本市场与储备。" 
        verify = f"需核实：摊薄股数口径（最近快照 {tracker_as_of or '—'}，上一期 {previous_as_of or '—'}）、可转债转换价、以及 8-K 发布节奏。"
        related = [f"官方追踪快照：{tracker_title or tracker_as_of or '—'}", "下一份 8-K 通常在一周内更新持仓与债务数据。"]
        confidence_note = "置信度基于来源完整度与新鲜度自动计算。"
    else:
        conclusion = (
            f"MSTR trades at mNAV {fmt(mnav, lambda x: _fmt_number(x, 3))}, a "
            f"{'premium' if (mnav or 1) >= 1 else 'discount'} of {fmt(abs((mnav or 1) - 1) * 100 if mnav is not None else None)}% to net BTC per share; "
            f"net leverage {fmt(net_leverage, lambda x: _fmt_number(x, 3))}, BTC reserve covers "
            f"{fmt(btc_years, lambda x: _fmt_number(x, 1))} years of interest+dividends."
        )
        bull = f"BTC yield YTD {fmt(btc_yield_ytd)}% with holdings still growing; while the mNAV premium persists, accretive issuance compounds BTC per share."
        base = f"Price and mNAV oscillate around net asset value; annual capital obligations ≈ {_fmt_usd(annual_dividends)} are covered by reserves, BTC 1Y return {fmt(one_year, lambda x: _fmt_pct(x, 0))}."
        bear = f"If mNAV flips to a discount while BTC falls (now {fmt(drawdown_from_ath, lambda x: _fmt_pct(x, 1))} from ATH), the accretive-issuance loop tightens and per-share gains slow; downside buffer ≈ {fmt(downside_buffer, lambda x: _fmt_pct(x, 1))}."
        hurdle = "Key uncertainty: software-segment earnings are absent from this feed, so obligations are analyzed purely against reserves and capital markets."
        verify = f"Verify: diluted-share methodology (latest snapshot {tracker_as_of or '—'}, prior {previous_as_of or '—'}), convert strike prices, and 8-K cadence."
        related = [f"Official tracker snapshot: {tracker_title or tracker_as_of or '—'}", "Next 8-K typically refreshes holdings and debt within a week."]
        confidence_note = "Confidence is computed from source completeness and freshness."

    completeness = 1.0
    if market_status != "live":
        completeness -= 0.25
    if tracker_status != "live":
        completeness -= 0.25
    if errors:
        completeness -= 0.1 * len(errors)
    confidence = max(0.1, round(completeness, 2))

    return {
        "asOf": kpis_as_of,
        "status": "live" if market_status == "live" and tracker_status == "live" else ("delayed" if market_status != "unavailable" or tracker_status != "unavailable" else "unavailable"),
        "confidence": confidence,
        "citations": [
            {"title": "Strategy — MSTR Metrics (official tracker)", "url": PAGE_URL, "publishedAt": tracker_as_of},
            {"title": "api.strategy.com — bitcoinKpis", "url": BITCOIN_KPIS_URL, "publishedAt": kpis_as_of},
            {"title": "api.strategy.com — mstrKpiData", "url": MSTR_KPI_URL, "publishedAt": kpis_as_of},
        ],
        "conclusion": conclusion,
        "bullCase": bull,
        "baseCase": base,
        "bearCase": bear,
        "biggestHurdle": hurdle,
        "assumptionsToVerify": verify,
        "relatedEvents": related,
        "evidenceGaps": gaps + ([confidence_note] if confidence < 1 else []),
    }


# ---------------------------------------------------------------------------
# Cache + series store
# ---------------------------------------------------------------------------

def _redis():
    from apps.api.redis_client import get_redis

    return get_redis()


def _series_load() -> list[dict[str, Any]]:
    try:
        raw = _redis().lrange(SERIES_KEY, 0, -1)
        return [json.loads(item) for item in raw]
    except Exception:
        logger.exception("mstr-btc: series load failed")
        return []


def _treasury_series_load() -> list[dict[str, Any]]:
    try:
        raw = _redis().lrange(TREASURY_SERIES_KEY, 0, -1)
        return [json.loads(item) for item in raw]
    except Exception:
        logger.exception("mstr-btc: treasury series load failed")
        return []


def append_series_point(pack: dict[str, Any]) -> None:
    """Append a market point (15-min dedup) and treasury snapshot points."""
    kpis = pack.get("kpis") or {}
    mstr = pack.get("mstr") or {}
    tracker = (pack.get("tracker") or {}).get("latest") or {}
    ts = _iso_utc(pack.get("kpis_timestamp") or kpis.get("timestamp")) or pack.get("fetched_at")
    if not ts:
        return
    point = {
        "ts": ts,
        "mstr": _num(mstr.get("ufPrice")),
        "btc": _num(kpis.get("ufPrice") or kpis.get("latestPrice")),
        "mnav": _num(kpis.get("mNav")),
        "reserves_usd_m": _num(kpis.get("btcNavNumber")),
        "liabilities_usd_m": (_num(mstr.get("debt")) or 0) + (_num(mstr.get("pref")) or 0) or None,
        "sats_per_share": _num(kpis.get("satsPerShare")),
        "capital_cost_usd": _num(kpis.get("totalAnnualDividends")),
    }
    try:
        redis = _redis()
        last_raw = redis.lindex(SERIES_KEY, -1)
        if last_raw:
            last = json.loads(last_raw)
            last_ts = datetime.fromisoformat(last["ts"])
            if (datetime.fromisoformat(ts) - last_ts).total_seconds() < SERIES_MIN_INTERVAL_SECONDS:
                pass  # too soon; skip market point but still try treasury below
            else:
                redis.rpush(SERIES_KEY, json.dumps(point))
                redis.ltrim(SERIES_KEY, -SERIES_MAX_POINTS, -1)
        else:
            redis.rpush(SERIES_KEY, json.dumps(point))
    except Exception:
        logger.exception("mstr-btc: series append failed")

    if tracker.get("as_of_date"):
        tpoint = {
            "ts": f"{tracker['as_of_date']}T00:00:00+00:00",
            "btc_yield_ytd": _num(tracker.get("btc_yield_ytd")),
            "btc_gain_ytd": _num(tracker.get("btc_gain_ytd")),
            "btc_holdings": _num(tracker.get("btc_holdings")),
            "debt": _num(tracker.get("debt")),
            "pref": _num(tracker.get("pref")),
        }
        try:
            redis = _redis()
            existing = _treasury_series_load()
            if not any(p["ts"] == tpoint["ts"] for p in existing):
                redis.rpush(TREASURY_SERIES_KEY, json.dumps(tpoint))
                redis.ltrim(TREASURY_SERIES_KEY, -500, -1)
        except Exception:
            logger.exception("mstr-btc: treasury series append failed")


def render_series() -> dict[str, list[dict[str, Any]]]:
    market_points = _series_load()
    treasury_points = _treasury_series_load()
    series: dict[str, list[dict[str, Any]]] = {
        "mstrPrice": [],
        "btcPrice": [],
        "mnav": [],
        "reserves": [],
        "liabilities": [],
        "btcYield": [],
        "btcGain": [],
        "btcExposurePerShare": [],
        "capitalCost": [],
    }
    for p in market_points:
        ts = p["ts"]
        if p.get("mstr") is not None:
            series["mstrPrice"].append({"timestamp": ts, "value": p["mstr"], "sourceUrl": MSTR_KPI_URL, "asOf": ts})
        if p.get("btc") is not None:
            series["btcPrice"].append({"timestamp": ts, "value": p["btc"], "sourceUrl": BITCOIN_KPIS_URL, "asOf": ts})
        if p.get("mnav") is not None:
            series["mnav"].append({"timestamp": ts, "value": p["mnav"], "sourceUrl": BITCOIN_KPIS_URL, "asOf": ts})
        if p.get("reserves_usd_m") is not None:
            series["reserves"].append({"timestamp": ts, "value": p["reserves_usd_m"], "sourceUrl": BITCOIN_KPIS_URL, "asOf": ts})
        if p.get("liabilities_usd_m") is not None:
            series["liabilities"].append({"timestamp": ts, "value": p["liabilities_usd_m"], "sourceUrl": MSTR_KPI_URL, "asOf": ts})
        if p.get("sats_per_share") is not None:
            series["btcExposurePerShare"].append({"timestamp": ts, "value": p["sats_per_share"], "sourceUrl": BITCOIN_KPIS_URL, "asOf": ts})
        if p.get("capital_cost_usd") is not None:
            series["capitalCost"].append({"timestamp": ts, "value": p["capital_cost_usd"] / 1_000_000, "sourceUrl": BITCOIN_KPIS_URL, "asOf": ts})
    for p in treasury_points:
        ts = p["ts"]
        if p.get("btc_yield_ytd") is not None:
            series["btcYield"].append({"timestamp": ts, "value": p["btc_yield_ytd"], "sourceUrl": PAGE_URL, "asOf": ts})
        if p.get("btc_gain_ytd") is not None:
            series["btcGain"].append({"timestamp": ts, "value": p["btc_gain_ytd"], "sourceUrl": PAGE_URL, "asOf": ts})
    return series


def refresh_fact_pack() -> dict[str, Any]:
    """Fetch fresh data, cache it, append series. Returns the pack."""
    pack = fetch_fact_pack()
    usable = bool(pack.get("kpis") or pack.get("mstr") or pack.get("tracker"))
    if usable:
        try:
            redis = _redis()
            redis.setex(CACHE_KEY, CACHE_TTL_SECONDS, json.dumps(pack))
            redis.setex(LASTGOOD_KEY, LASTGOOD_TTL_SECONDS, json.dumps(pack))
        except Exception:
            logger.exception("mstr-btc: cache write failed")
        append_series_point(pack)
    return pack


def _load_cached(key: str) -> dict[str, Any] | None:
    try:
        raw = _redis().get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def get_dashboard(locale: str = "en") -> dict[str, Any]:
    """Cache-first dashboard: fresh pack -> cache -> last-good -> unavailable."""
    pack = _load_cached(CACHE_KEY)
    served_from = "live"
    if pack is None:
        acquired = False
        try:
            acquired = bool(_redis().set(LOCK_KEY, "1", nx=True, ex=15))
        except Exception:
            acquired = True  # no redis -> just build inline
        if acquired:
            try:
                pack = refresh_fact_pack()
            finally:
                try:
                    _redis().delete(LOCK_KEY)
                except Exception:
                    pass
        else:
            deadline = time.time() + 3
            while time.time() < deadline and pack is None:
                time.sleep(0.25)
                pack = _load_cached(CACHE_KEY)
        if pack is None:
            pack = _load_cached(LASTGOOD_KEY)
            served_from = "last_good" if pack else "live"
    elif pack is not None:
        served_from = "cache"

    series = render_series()
    if pack and (pack.get("kpis") or pack.get("mstr") or pack.get("tracker")):
        return build_dashboard(pack, locale, series=series, served_from=served_from)

    # hard-unavailable contract (no fabrication)
    reason = "strategy_sources_unreachable" if locale != "zh" else "Strategy 数据源不可达"
    return {
        "asOf": None,
        "sourceStatus": "unavailable",
        "sourceUrl": PAGE_URL,
        "metrics": [],
        "series": series,
        "scenarios": [],
        "research": None,
        "notes": [
            ("Live and cached Strategy data are both unreachable. Showing no fabricated values." if locale != "zh" else "实时与缓存的 Strategy 数据均不可达，不展示任何虚构数值。"),
            reason,
        ],
        "unavailable": True,
        "error_code": "SOURCE_UNAVAILABLE",
    }
