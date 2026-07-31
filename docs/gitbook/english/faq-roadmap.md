# FAQ & Roadmap

## Troubleshooting

**Voice won't play?**
1. Tap the play button on the reply — autoplay is often blocked by the browser; a manual tap always works (audio is cached).
2. Read the error text: "insufficient credits" → upgrade or wait; "too many requests" → retry in a minute; "service unavailable" → the voice upstream is down, text replies still work.
3. Long replies are truncated to 1500 characters for speech — the full answer is always in text.

**Login problems?**
- Slider: release near the notch; refresh for a new image; arrow keys + Enter also work.
- "Too many attempts": 15-minute rate limit — wait and retry.
- No verification email: check spam; resend from the login page.
- Redirected to login: session expired; you return to the original page after signing in.

**Data issues?**
- Stalled market data: provider outages are flagged explicitly; stale data is never presented as live.
- Slow Agent answers: deep research calls multiple tools; the stream shows progress and can be stopped.
- Missing daily brief: check push preference, timezone and that it's been at least one night since signup.

**Billing?**
- 402 = out of credits. Failed tasks auto-refund via the reserve/settle pipeline.

## Roadmap

Hidden capabilities already live: Backtest Lab (Research sidebar), iMessage Agent (Account), Autopilot portfolio review, Earnings Gamma, and an internal admin console.

System design principle: **components call each other** — one memory layer feeds Secretary, Agent, briefs and backtest spec generation; one skills library serves chat and reports; one credits pipeline handles reservation/settlement/refunds; one dispatcher handles all notification channels.

Planned: strategy marketplace (share & reuse backtest specs), more data sources, intraday backtesting, app store releases, a public research API, and more languages. The roadmap is directional, not a commitment.
