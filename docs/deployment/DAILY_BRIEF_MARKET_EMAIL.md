# Daily brief e-mail: market brief content and rendering

The scheduled daily brief keeps its users, preferences, delivery times, credits, idempotency keys and
recipient binding. Only the **e-mail** channel changes:

1. **Content.** When the `market-brief` sidecar has a fresh brief, the e-mail is the Coinbase/Nasdaq
   market brief for the user's locale (zh/en): subject, email-safe HTML and plain text come from the
   sidecar. The personalised reports are still generated and still reach the web inbox and the other
   channels.
2. **Fallback.** If the sidecar is unreachable, answers with an error, returns something invalid or a
   brief older than `MARKET_BRIEF_MAX_AGE_SECONDS` (default 7200), the e-mail is the consolidated report
   digest as before, now with a dated subject ("PureGamma AI Daily Brief · Oct 29").
3. **Rendering.** `branded_email_html` renders the digest's light Markdown (headings, bold/italic,
   code, links, lists, quotes, rules, pipe tables) instead of showing `##`/`**` literally, and the header
   is a text wordmark (the monochrome PNG logo was invisible on the dark header and shown broken by
   some clients).

## Moving parts

| Piece | Where | Notes |
| --- | --- | --- |
| `packages/notifications/market_brief.py` | worker | `fetch_market_brief(locale)`: 8 s timeout, shape checks, HTML ≤ 400 KB, 120 s per-locale cache, 60 s back-off after a failure, never through a proxy. Returns `None` on any problem. |
| `packages/workers/tasks.py` | worker | `_daily_brief_email` picks the market brief or the digest for the e-mail branch of `_process_due_preference`. |
| `packages/notifications/dispatcher.py` | worker | Passes `email_subject` / `email_html` metadata to the e-mail provider only. Deliveries still store just the plain-text message. |
| `packages/notifications/email.py` | worker, api | Markdown rendering, text wordmark, optional pre-rendered HTML and subject. |
| `MARKET_BRIEF_URL` | worker env | Defaults to `http://market-brief:8790` in `docker-compose.production.yml`; set it to an empty value to turn the market brief off. |
| `market-brief` sidecar | `/puregamma/market-brief` | `market_report.py` from [puregamma-event-collector](https://github.com/xxxxxwater/puregamma-event-collector) run headless (`deploy/market-brief/compose.yaml`): public data only, no secrets, no personal data, no host port. It is its own compose project, so `deploy.sh` (`up --remove-orphans`) never removes it. |

Sidecar contract: `GET /brief?locale=zh|en` → `200 {ok, locale, snapshot_id, taken_at, age_seconds,
subject, html, text, parts}`, or `503` when there is no usable snapshot and `400` for an unknown locale.
`GET /health` reports heartbeat, snapshot age and collection-job health.

## Operator commands (worker image)

```sh
C="docker compose --env-file .env -f docker-compose.production.yml"
$C run --rm --no-deps worker python -m packages.notifications.market_brief --check
$C run --rm --no-deps worker python -m packages.notifications.market_brief --preview /tmp/brief.html --locale zh
$C run --rm --no-deps worker python -m packages.notifications.market_brief --test-send you@example.com --locale both
```

`--test-send` takes exactly one address and prefixes the subject with "[Test]" / "[测试]".

## Rollout

1. Start the sidecar and wait until `/health` is OK and `--check` prints `ok` for both locales.
2. Tag the running worker image for rollback, build only the worker (`$C build worker`), and send a test
   e-mail to yourself with the new image.
3. Recreate only the worker: `$C up -d --no-deps --no-build worker`. No migration; api and scheduler are
   untouched.

## Rollback

- **Content only:** stop the sidecar (`docker compose -p market-brief stop`). Within two minutes the daily
  brief e-mails fall back to the report digest with the new rendering.
- **Everything:** revert this change, retag the previous worker image as `puregamma-ai-worker:latest` and run
  `$C up -d --no-deps --no-build worker`.
