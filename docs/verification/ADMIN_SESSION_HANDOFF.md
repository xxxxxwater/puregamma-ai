# Admin session handoff (credential-free)

How to obtain, verify, use and clean up a **real administrator session** for
acceptance testing of `/admin/*`, without putting any credential in Git.

This document exists because the admin session has repeatedly been treated as a
blocker that has to be rediscovered. Everything below is derived from the running
code, with file and line references, so it can be re-checked rather than trusted.

---

## 1. The normal authentication path

There is exactly one normal path worth using for acceptance: the **email +
password form login**, because it is the path a real operator uses.

| Step | What happens | Where |
| --- | --- | --- |
| 1 | `POST {API}/auth/email/login` with `{email, password, captcha_id, captcha_offset}` | `apps/api/routers/email_auth.py:294` |
| 2 | Email normalised and format-checked; **captcha verified**; rate limit 5 per email per 900s | `email_auth.py:301-307` |
| 3 | Password verified with `verify_password`; a wrong password returns `401 INVALID_CREDENTIALS` | `email_auth.py:310-314` |
| 4 | Unverified email returns `403 EMAIL_NOT_VERIFIED` | `email_auth.py:316` |
| 5 | **`user.session_version += 1` then commit** | `email_auth.py:319-322` |
| 6 | `set_session_cookie(response, user)` issues the JWT as an httpOnly cookie | `apps/api/dependencies.py:105-118` |
| 7 | Response body is `{"user": {...}}` — the **only** place the browser learns its own role | `email_auth.py:326` |

**The captcha is part of the normal path.** Confirm the enabled captcha provider
before scripting anything; if it cannot be satisfied headlessly, use the real UI
login form instead. Never disable captcha in production to make a test pass.

### Why this matters for a saved session

Step 5 means **logging in invalidates every previously issued token for that
account**, including one you saved five minutes ago. Requesting a fresh login is
therefore not a retry — it is the documented behaviour.

## 2. The session cookie contract

`apps/api/dependencies.py:105-118`, with names from `apps/api/config.py:121-122`:

| Attribute | Value | Consequence |
| --- | --- | --- |
| name | `SESSION_COOKIE_NAME`, default `pg_session` | — |
| `domain` | `SESSION_COOKIE_DOMAIN` | **Must be a parent of `SITE_URL`**; validated at startup (`config.py:934-942`) |
| `path` | `/` | — |
| `httponly` | `true` | JavaScript cannot read it; a storageState file is the only way to replay it |
| `secure` | `true` when `APP_ENVIRONMENT=production` | HTTPS only |
| `samesite` | `lax` | Sent on same-site navigation and top-level GET |
| `max_age` | `SESSION_MAX_AGE_SECONDS` | See expiry handling below |

### The browser-context requirement that has cost the most time

`app.puregamma.ai` and `api.puregamma.ai` are **two hosts**. The cookie is issued
by the API and is only sent to the app because it is scoped to the registrable
domain (`.puregamma.ai`).

A Playwright cookie added with `{ url: "https://api.puregamma.ai" }` is
**host-only**: the browser never sends it to `app.puregamma.ai`, `/me` answers
`401`, and the client watchdog bounces the session to `/login`. Correct form:

```js
await context.addCookies([{
  name: "pg_session", value: <token>,
  domain: ".puregamma.ai", path: "/",
  httpOnly: true, secure: true, sameSite: "Lax",
}]);
```

Anything asserting "admin access works" must be able to state which of these two
it exercised.

## 3. Confirming the administrator role

Two independent checks; do both, because they fail differently.

1. **Who am I.** `GET {API}/me` (or the login response body) must report
   `user.role === "admin"`. If it reports any other role, the session is valid but
   is not an admin session — that is the case that must be *reported*, not worked
   around.
2. **What the server enforces.** `require_admin` rejects any non-admin with
   `403` (`apps/api/dependencies.py:128-130`), and every `/admin/*` endpoint
   depends on it. A `403` proves the gate is live; it never proves the caller is
   an admin.

`GET {API}/admin/overview` is the cheapest positive proof: `200` with a
`generated_at` and a `counts` object. `401` means "no usable session"; `403` means
"authenticated, not an admin". The two must be reported separately.

## 4. Test state: where it lives and how it is cleaned up

No session artifact exists in this repository today, and `.gitignore` did not
previously exclude one. Both are now true:

- A captured browser session belongs in `tests/e2e/.auth/` (git-ignored).
- `.auth/` and any `storageState` JSON are excluded via `.gitignore`.
- **Never commit**: `pg_session` token values, any cookie value, passwords,
  `storageState` JSON, or captured `Set-Cookie` headers. A committed session is a
  live credential and, per section 1, invalidating it also logs the account out.

To capture state for a run, perform the login **once, interactively, in a real
browser** and let the test tool write the file. Do not paste the credential into
the repository, a script, a spec, or a chat message.

Cleanup after acceptance:

```powershell
Remove-Item -Recurse -Force tests/e2e/.auth
```

Then confirm it is untracked: `git status --porcelain tests/e2e/.auth` prints
nothing.

## 5. When the session expires

`get_current_user` rejects with `401` in three distinct situations
(`apps/api/dependencies.py:88-95`):

| Symptom | Cause | Action |
| --- | --- | --- |
| `401` with no cookie in the request | Session file missing, or cookie scoped to the wrong host (section 2) | Re-capture the session |
| `401 "Session has been revoked"` | `session_version` no longer matches the token — someone logged in again | Re-capture the session; this is expected, not a defect |
| `401` after `SESSION_MAX_AGE_SECONDS` | Token genuinely expired | Re-capture the session |

The frontend reacts to any of these by redirecting to login
(`apps/web/lib/api.ts` → `notifyAuthExpired`, gated on
`requiresAuthentication()` so public pages are left alone). A redirect during an
admin assertion is therefore **an expired session**, not a broken admin page.

**Never assume a previously captured session is still valid.** Any acceptance run
that needs admin access must start by confirming `/admin/overview` returns `200`
with the admin role, and must request a fresh interactive login if it does not.

## 6. Requesting a login (what to ask the operator for)

Ask exactly this, once, before the acceptance run:

> Please log in normally at `https://app.puregamma.ai/{locale}/login` in the
> browser window I am about to open. Do not send me the password.

The operator types the password into the real form. Nothing about the credential
enters the chat, a file, or a command. If the browser window has closed, ask
again rather than reusing a stale capture.

## 7. The two results that must be reported separately

These are **not** interchangeable and must never be summarised as one another:

- **Pre-authorised session access** — a session obtained from an already
  authenticated context. Proves the admin API and UI work when a valid cookie is
  present.
- **Normal login form flow** — the operator actually typed the password into
  `/login`. Proves the login path itself, including captcha, session issuance and
  the `session_version` bump.

A green run of the first says nothing about the second.

## 8. Admin acceptance checklist (read-only)

Run against the released production build, in this order:

1. **Login** — normal form flow; land authenticated.
2. **Overview** — `/admin/overview` returns `200`; `generated_at` present.
3. **Billing intents** — `/admin/billing-intents` with a **status filter**, page
   forward and back; verify `total` matches the rendered rows and that changing
   the filter resets to the first page.
4. **Stripe events** — `/admin/stripe-events`, filter on **both** `processed` and
   `manual_review` (tri-state: unset must differ from `true` and from `false`);
   verify `total` and paging.
5. **Refresh** — reload; filters and page position survive or reset predictably.
6. **Deep link** — open a subpage URL directly in a fresh tab; no login redirect.
7. **Logout** — exit; `/admin/*` afterwards must answer `401`/redirect.
8. **Non-admin still refused** — repeat step 3 with a normal user's session;
   expect `403`, not `200` and not `401`.

**Read-only means read-only.** Do not mutate real balances, do not replay payment
events, do not delete business data.

### Backend contract already live (for the frontend's paging work)

| Endpoint | Filters | Additive meta |
| --- | --- | --- |
| `/admin/users` | `q`, `role`, `plan` | `total/limit/offset/page/has_more` |
| `/admin/billing-intents` | `status` | same |
| `/admin/stripe-events` (alias `/admin/stripe/events`) | `processed`, `manual_review` | same |
| `/admin/notifications` | `status`, `channel` | same |
| `/admin/data-sources/{provider}/runs` | `status` | same |

`limit` is clamped to `1..100`; `limit=101`, `limit=0` and `offset=-1` return
`422`.
