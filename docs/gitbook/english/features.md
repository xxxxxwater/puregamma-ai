# Feature Guide

Features are organized around the Beta / Alpha / Long Gamma narrative.

## Dashboard & Daily Brief

- **Dashboard (Today)**: live market snapshot with per-asset source and freshness flags, latest research reports, and your plan status. When a provider is down the UI says so explicitly — it never fabricates data.
- **Daily Brief**: a research brief generated every day. A default preference (email, 08:30, your timezone) is created automatically; delivery is idempotent per day per channel. You can also generate it manually from the Reports page (costs credits; same-day regenerations hit cache).
- **Channels**: Email (default), Telegram, Slack, iMessage (Max/Enterprise), iOS push.

## Agent Chat

Streaming research assistant with tool calls and citations:

- Conversations with history, archiving and multi-session support; stop/cancel anytime.
- **Advanced research settings** (collapsible panel): model picker, data scopes (live market REST, RSS news, X/Twitter), skill selection, custom prompt, attachments (≤20KB each, ≤50KB total).
- **Skills** are versioned research playbooks upgraded server-side: market_research, news_research, portfolio_review, options_analysis, source_check, deep_research.
- Runs consume credits; cancellations settle by actual usage. Per-plan daily run and concurrency limits apply.

## Private Secretary (voice)

Your private companion with persistent long-term memory — it remembers your preferences and past discussions across sessions:

- Text chat (up to 4000 chars) with streaming replies.
- **Voice**: tap the mic to record, tap again to transcribe and send; every reply has a play button for its spoken version.
- **Autoplay**: the newest reply tries to autoplay. Browsers may block autoplay without a recent gesture — that is not an error; just tap the play button (audio is cached and starts instantly).
- Voice synthesis costs 2–8 credits per message by length; on insufficient credits the text reply still arrives and a clear upgrade prompt is shown. Long replies are truncated at 1500 chars (sentence boundary preferred) for speech.

## Options Research

- **Long Gamma candidates** for BTC/ETH from Deribit chains: expiry, strike, premium, IV and score. Research only — trade at your own venue.
- **Earnings Gamma** for US equities with an ~8-day cache to control LLM cost.

## Backtest Lab (hidden gem)

Sidebar → Research → Backtest. Turns "ideas from your chats" into verifiable strategies:

1. **Data**: 3 years of BTC/ETH daily candles (Binance), shared platform-wide, incrementally updated nightly.
2. **Spec generation**: an LLM turns your idea (optionally with chat memory) into a validated strategy spec you can edit.
3. **Engine**: daily-frequency (momentum / mean-reversion / breakout) and cross-sectional long-short templates with fees, stops, turnover and next-open fills — no look-ahead.
4. **Performance**: cumulative return, Sharpe, max drawdown, win rate, turnover, exposure, tail loss, equity curve and per-asset breakdown.

Limit: 5 runs per user per day. Backtests are historical simulations, not predictions.

## Portfolio & Connections

NAV, cash, holdings, daily change and history. All connections are **read-only** — no orders, transfers or keys:

- Plaid (brokerage/bank), IBKR (OAuth), Hyperliquid (public address), EVM wallet (Moralis).
- Stale or failed connections are flagged explicitly.
- **Autopilot**: read-only risk review (concentration, unusual exposure, data anomalies) — research findings, never auto-execution.

## Notifications & iMessage

Channels honor plan entitlements; unknown channel names are rejected with a validation error.

**iMessage Agent** (Max/Enterprise): bind a phone number (E.164) or Apple ID email → a 6-digit code arrives via iMessage (valid 10 min) → confirm to activate. Then text the official number to chat with your Agent and receive briefs. Verification requests are rate-limited (3/hour per user, 5/day per recipient); inbound messages are HMAC-signed with replay protection; only your verified address is answered.
