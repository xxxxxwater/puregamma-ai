# PureGamma iOS delivery report

Date: 2026-07-15

Status: P1 code complete; production credentials and signed physical-device E2E
remain external release gates.

## Completed iOS modules

- Swift 6, SwiftUI, Observation, async/await, URLSession, MVVM + Repository.
- Five-tab consumer navigation: Today, Agent, Research, Portfolio and Account.
- Shared design system with restrained terminal styling, monospaced financial
  figures, dark/light appearance, Dynamic Type, VoiceOver labels and English /
  Simplified Chinese resources.
- DTO/domain separation, Decimal account and option values, UTC decoding and
  device-time-zone presentation.
- Keychain-only bearer token storage and automatic local session removal on
  HTTP 401.
- Native Google sign-in through ASWebAuthenticationSession with state, nonce,
  PKCE and a single-use server exchange code.
- Native Sign in with Apple through AuthenticationServices with a per-request
  hashed nonce and server-side authorization-code exchange. No Apple private
  key or refresh token is stored in the app.
- Today real market snapshot, report list and server-owned credits/plan state.
- Agent conversation CRUD, model/data-source/skill/prompt/attachment controls,
  all documented SSE events, citations, cancellation, reconnect/reload states,
  and explicit 402/403/429/503 handling. Streaming does not force scroll
  position changes.
- Research reports and Deribit long-gamma research for BTC and ETH.
- Portfolio snapshot, real NAV/cash/history, draggable full-width crosshair,
  range selection, stale/empty states, Plaid LinkKit 7, IBKR system-browser
  handoff, public-address-only Hyperliquid connection and research-only
  Autopilot review.
- Account plan, credits, billing status, daily brief settings, language,
  appearance, legal/support links, logout and destructive account deletion.
  Purchases remain disabled pending App Store review.
- Unit test sources for PKCE, DTO/Decimal/UTC decoding and all Agent SSE event
  types; UI test source for large Dynamic Type and login accessibility.
- Separate Debug/Release configuration, production HTTPS enforcement, a clean
  Release transport policy, AppIcon asset and Apple privacy manifest.
- File-protected cache of previously returned real market, report and portfolio
  responses. Offline fallback is visibly labelled with its saved timestamp and
  is never presented as current data; cache is cleared on 401/logout/deletion.
- Native APNs permission, token registration, foreground presentation and
  notification-route handling. Daily Brief can use the backend-authorized
  `push` channel.
- IBKR mobile OAuth through ASWebAuthenticationSession, an HTTPS backend
  callback and authenticated single-use app completion code.
- Agent retry now retains the failed Prompt and its context snapshot, uses the
  selected app locale, hides retry for permission/payment failures, limits
  attachments to 20 KB each/50 KB total, and exposes only server-authorized
  data sources.

## Backend changes

- Added `/auth/mobile/google/start`, `/auth/mobile/google/callback` and
  `/auth/mobile/google/exchange` without changing the Web HttpOnly-cookie flow.
- Added allowlisted mobile callback configuration and a short-lived persisted
  `MobileOAuthSession` with Alembic migration `0008_mobile_oauth_sessions.py`.
- Reused the existing Google identity verification and user upsert path.
- Added single-use exchange, state, nonce and PKCE regression tests.
- Added `POST /auth/mobile/apple/exchange`, Apple identity-token verification,
  server-only ES256 client-secret generation, encrypted provider credential
  storage and provider revocation support.
- Added `DELETE /me` with explicit email confirmation, external Apple/Stripe
  cleanup and deletion of directly and transitively user-owned database data.
- Added `UserIdentity.credential_ciphertext` and Alembic migration
  `0009_apple_identity_credentials.py`.
- Added production privacy and terms pages to the existing marketing site.
- Added encrypted APNs device registration/unregistration, APNs HTTP/2 provider,
  invalid-token disabling, push entitlements and server-owned delivery status.
- Added a replay-resistant mobile IBKR start/callback/complete flow while
  retaining the existing Web IBKR flow.
- Added `PushDevice` and Alembic migration `0010_push_devices.py`; the migration
  chain has a single head.

## Validation

- Generic physical-device arm64 application build: succeeded.
- Generic physical-device arm64 Release build: succeeded. The packaged app uses
  `https://api.puregamma.ai` and contains no ATS exception.
- Generic physical-device unit/UI test bundle build: succeeded.
- P1 generic physical-device Debug and Release builds: succeeded.
- P1 unit/UI test bundles, including the protected-cache test, compiled for
  physical-device arm64.
- Full backend pytest suite: succeeded, including existing expected-failure
  markers.
- Apple/mobile-auth/account-deletion focused suite: 6/6 passed.
- P1 APNs/IBKR/entitlement/configuration focused suite: 29/29 passed.
- Marketing-site build and tests: succeeded; `/privacy` and `/terms` are emitted.
- Privacy plist/entitlements validation: succeeded. The 1024 px AppIcon is
  opaque and the app privacy manifest is present in the Release product.
- Development API health: HTTP 200.
- Mobile Google OAuth start against the updated development server: HTTP 200,
  producing an `accounts.google.com` authorization URL.
- Public options endpoint: HTTP 200. Protected reports and portfolio endpoints
  correctly returned HTTP 401 without a bearer token.
- A fresh real market request timed out at the upstream provider during the
  final probe; no mock or fallback price was substituted.

## Third-party configuration still required

- Register the production HTTPS mobile Google callback and set
  `MOBILE_GOOGLE_OAUTH_REDIRECT_URI` / `MOBILE_OAUTH_REDIRECT_URIS`.
- Configure the Xcode Apple Development team and signing profiles. Enable Sign
  in with Apple for `ai.puregamma.ios`, then configure `APPLE_TEAM_ID`,
  `APPLE_KEY_ID` and the server-only `APPLE_PRIVATE_KEY`.
- Configure push entitlement and production APNs credentials.
- Set `APNS_ENABLED=true`, `APNS_TEAM_ID`, `APNS_KEY_ID`, `APNS_BUNDLE_ID` and
  the server-only `APNS_PRIVATE_KEY`; install the updated HTTP/2 dependency.
- Plaid Link is compiled but requires valid server Plaid credentials and a
  production Link configuration.
- IBKR requires production OAuth credentials/callback approval. Hyperliquid
  remains public-address/read-only.
- Register `https://api.puregamma.ai/portfolio/ibkr/mobile/callback` with IBKR
  and configure `MOBILE_IBKR_OAUTH_REDIRECT_URI` plus the allowlisted app URI.
- StoreKit products and purchase UI are intentionally absent until App Store
  commercial-compliance review is complete.

## App Store / end-to-end blockers

- The paired iPhones are currently reported unavailable by Xcode command-line
  tools. The already-built unit/UI bundles must still execute on a signed
  physical device; no simulator was used.
- Complete real Apple and Google login callbacks, an authenticated Agent SSE
  run, Plaid Link, IBKR OAuth and push delivery against staging/production.
- Execute notification permission denial/approval, APNs sandbox/production
  token rotation, logout unregistration and notification-tap routing on a
  signed physical iPhone.
- Deploy the new `/privacy` and `/terms` routes at `puregamma.ai`, complete legal
  review of privacy/risk/account-deletion wording and fill App Store privacy
  disclosures consistently with the manifest and backend behavior.
- Finalize App Store metadata, screenshots, support contact, age rating and
  export-compliance answers.
- Validate upstream market reliability and stale-data alerting before release.
- Complete App Store commercial review and StoreKit product design before
  exposing any iOS purchase action. Web Stripe Billing remains server/web-only;
  Stripe Checkout is intentionally not copied into the iOS app.
