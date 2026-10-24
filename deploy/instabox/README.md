# PureGamma AI on Instabox `pg-test`

This deployment is an isolated SaaS preview on the existing `pg-test` box. The original display server and `app.puregamma.ai` routing are outside this deployment. Existing PG-TSY, collector, translation, VPN, and other containers on `pg-test` must remain running.

## Layout

| Item | Location or service |
| --- | --- |
| Code checkout | `/data/home/puregamma-ai-preview/source` (`origin/main`) |
| Private database, uploads, Redis data, secrets, Caddy config | `/data/private/puregamma-ai-preview/` |
| API | `pg-ai-preview-api.service` at `127.0.0.1:8100` |
| Web | `pg-ai-preview-web.service` at `127.0.0.1:3101` |
| Edge | `puregamma-ai-preview-edge` on host port `3100`, HTTPS through Instabox, Basic Auth at the edge |
| Redis | `puregamma-ai-preview-redis` at `127.0.0.1:16379` |

Private data is never committed to the public GitHub repository. The migrated SQLite database contains the local users and conversation records; its original snapshot and pre-migration snapshots are retained in the private directory. Upload storage is mounted there as well. The archived server backups under `archives/` are preserved and were not restored into the active database.

## Release procedure

1. Commit and push reviewed code to `main`. Confirm the intended revision with `git ls-remote origin refs/heads/main`.
2. On `pg-test`, check free space on `/` and `/data`, available memory, existing container health, and port ownership. Record any pre-existing unhealthy service before changes.
3. Pull `main` into the preview checkout with `git pull --ff-only`. Back up `active.db` using SQLite's backup API, then apply Alembic migrations with the private `DATABASE_URL`. Check `PRAGMA quick_check`, user count, and `alembic_version` before starting the new API.
4. Build the Web into a new directory with `NEXT_PUBLIC_API_URL=/__api` and `NEXT_DIST_DIR=.next-build-new`. Do not build in the directory currently served by Web.
5. Stop only `pg-ai-preview-web.service`. Move `.next-build` to `.next-build-prev`, move `.next-build-new` to `.next-build`, then start Web. Restart only `pg-ai-preview-api.service` when backend code changed. Keep the previous Web build for rollback.
6. Verify `/health`, `/ready`, `/en`, `/zh`, `/en/login`, `/en/chat`, `/en/gateway`, and `/en/api` through the Basic Auth edge. Verify that mock login and mock billing routes remain closed, model capabilities and Gateway catalog return their expected entries, and the pre-existing containers/ports are unchanged.

If Web fails, swap `.next-build-prev` back and restart only the Web service. If a migration fails, stop only the preview API and restore the captured private database backup before retrying. Never restore the archived production backups over `active.db` without a separate data reconciliation.

## Current preview limits

- Instabox enforces a 30-minute idle suspension for this box, so this URL cannot be treated as an always-on production endpoint.
- The migrated users were Google-authenticated; Google OAuth has no registered callback for the Instabox preview origin. The internal admin login is for verification only.
- Billing, public mock login, mock webhook, Gateway request forwarding, live trading, and workers are disabled in this preview. Model selection and catalog display use the existing upstream configuration and default model.
- The preview URL and access credentials live in a local private access file outside this repository. Never put them in commits or deployment logs.
