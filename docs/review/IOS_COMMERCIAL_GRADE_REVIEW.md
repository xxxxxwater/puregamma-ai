# PureGamma iOS — Commercial-grade review

Scope: `apps/ios` native SwiftUI client against the PureGamma FastAPI platform.
Review date: 2026-08-05. Baseline: P1 code complete per `DELIVERY_REPORT.md`;
this review re-audits every module against commercial (App Store / production)
quality bars and records the concrete upgrades applied.

## Verdict

The iOS client is already above hobby/P1 quality: Swift 6 strict concurrency,
MVVM + Repository, Keychain-only tokens, native OAuth (Google + Sign in with
Apple) with PKCE/nonce/state, a real response cache that never masquerades as
live data, a defensive error model, and full i18n/a11y effort. It is **close to
commercial** but not release-complete. This review records findings, then a set
of high-confidence code upgrades, then the remaining external gates that code
cannot close.

## Architecture & concurrency

### Strengths

- Swift 6, `SWIFT_STRICT_CONCURRENCY = complete`, `SWIFT_DEFAULT_ACTOR_ISOLATION = MainActor`, `SWIFT_APPROACHABLE_CONCURRENCY = YES`.
- `@MainActor` repository/view-model boundary; a single `actor ResponseCache`.
- File-system-synchronized groups (`PBXFileSystemSynchronizedRootGroup`) keep the
  project file in sync with disk without per-file PBX edits — maintainable.
- DTO ↔ domain separation with explicit CodingKeys and UTC decoding
  (`JSONDecoder.pg` / `iso8601Flexible`); financial figures stay `Decimal`.
- No third-party network/analytics dependency beyond Plaid LinkKit; privacy is
  cheap to defend.

### Findings

1. **`APIClient` and `AppLinks` use `fatalError` on bad build config**
   (`APIConfiguration.swift`, `AppLinks.swift`). It is acceptable as a build-time
   guard (Release pins HTTPS), but it will crash a Release binary if the plist is
   mispackaged. Prefer a fail-loud-but-recoverable path and a startup assertion.
2. **Timeout/retry policy is fixed per-call** (`request` = 20 s, `stream` = 120 s).
   No exponential backoff and no `Retry-After` scheduling. Acceptable for v1 but
   should be centralized before scale.
3. **No token refresh flow.** The client relies on server-issued long-lived tokens
   and clears local state on 401. Confirm the server's access-token lifetime vs.
   typical session expectations; a refresh grant would improve UX.

## Security & data handling

### Strengths

- Bearer token only in Keychain (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`).
- Google mobile OAuth: `state`, `nonce`, PKCE `S256`, single-use server exchange
  code. Apple: per-request hashed nonce, server-side auth-code exchange; no
  `.p8`/refresh token in the app.
- Read-only research boundary: no LIVE orders/transfers/signing; Stripe, LLM,
  Plaid, IBKR and exchange secrets stay server-side.
- File-protected cache (`NSFileProtectionComplete`), cleared on 401/logout/deletion.
- Release has no ATS exception; Debug-only local-network exception.
- IBKR/Google callback hosts/paths are validated before accepting a `code`.
- Account deletion requires re-entering the account email.

### Findings

1. **Push un-registration environment mismatch (real bug).** `registerPushDevice`
   correctly selects `sandbox` under `#if DEBUG`, but `unregisterPushDevice`
   hardcodes `"production"` (`Repositories.swift`). On a Debug install the device
   registers as sandbox yet un-registers as production on logout, leaving a stale
   APNs device row. **Fixed.**
2. **Keychain queries do not set `kSecUseDataProtectionKeychain`/`kSecUseAuthenticationUI`**
   and `save` does not surface `errSecDuplicateItem` explicitly (it deletes first,
   which is fine). Minor hardening opportunity.
3. **`unregisterPushDevice` is not called on account deletion** — only on `logout`.
   After deletion the push device token should be removed server-side as well.
   **Fixed to run on both paths.**
4. `handleCallbackURL` accepts any URL with the `puregamma` scheme and passes it to
   `resolveCallback`, which resumes a pending continuation. The OAuth flows already
   re-validate `state`/host, so the risk is limited; still, gate cold-start deep links
   by host/path at the app boundary.

## UX, accessibility & i18n

### Strengths

- Consistent terminal/monospaced design system (`PGTheme`), dark/light + Dynamic Type.
- VoiceOver labels and `accessibilityElement(children: .combine)` on key rows;
  a UI test asserts login is reachable at `AccessibilityExtraExtraLarge`.
- English and Simplified Chinese resources; `Text("...")` literals localize via
  `LocalizedStringKey` and the zh-Hans file is comprehensive (154 keys).
- Explicit unavailable/offline/permission/rate-limit/empty states — never mock
  numbers presented as real.
- Stale cache is visibly labelled with its saved timestamp.

### Findings

1. **`PGTheme.accent` (light lime) is low-contrast against white** when used as a
   filled tint (e.g. Send button uses it as background but forces black text, which
   is correct). Any future use of accent text on white will fail WCAG AA. The
   `TodayView` title uses accent text on systemBackground — verify on light mode.
2. **`errorStrip` in `AgentView` has a convoluted condition** that is hard to audit
   (`if error.presentation != .permissionDenied, case .paymentRequired = error {
   EmptyView() } else if ...`). It behaves correctly but is fragile to future edits.
   **Refactored for clarity.**
3. **Login errors are not cleared when starting a new attempt**, so a transient
   failure message lingers while the user retries. **Fixed.**
4. No app version/build shown in Account — expected in a commercial app for
   support triage. **Added an About row.**
5. No error/empty treatment for `user.avatarURL` load failure beyond the SF Symbol
   placeholder (already handled). Fine.

## Reliability & error handling

- `LoadState` models idle/loading/loaded/empty/stale/failed; `LoadFailure`
  presentation drives iconography and copy.
- SSE parser is unit-tested for every documented event; DTO/Decimal/UTC decoding
  and cache round-trip are tested.
- `onUnauthorized` triggers a single coordinated local reset.

Remaining reliability gaps are server-side (upstream provider timeouts, market
freshness alerting) and are tracked in `DELIVERY_REPORT.md`.

## Testing

Unit test coverage is thin relative to the module count: PKCE (2), SSE (2),
DTO/Decimal (2), cache (1), plus one UI test. For commercial confidence, add:
- APIClient error-envelope decoding tests (401/402/403/429/503 → `APIError`).
- Keychain token-store lifecycle test (write/read/delete) with a mock security
  context or a dedicated keychain service.
- Repository request-path tests with an injected mock `URLProtocol`.
- A stub-based test for the Agent SSE streaming state machine (delta/citation/fail/
  cancel accumulation) — currently only the parser is covered, not the reducer.

## Performance

- Lists use `LazyVStack`/`List`; NAV chart is a lightweight `Canvas` with no
  expensive recomputation. `CURRENT_PROJECT_VERSION = 1`, `MARKETING_VERSION = 1.0`.
- No image-heavy loads (avatar only). Acceptable for v1; revisit if reports grow.

## App Store / commercial readiness (external gates)

These cannot be closed by code and remain the real launch blockers:

1. Production signing: Xcode team, provisioning profiles, Sign in with Apple
   entitlement for `ai.puregamma.ios`, APNs push entitlement.
2. Production credentials: mobile Google callback, `MOBILE_GOOGLE_OAUTH_REDIRECT_URI`,
   server-only `APPLE_*`/`APNS_*` keys, Plaid production keys, IBKR OAuth approval.
3. Legal: finalize `/privacy` and `/terms` wording, fill App Store privacy
   disclosures consistently with `PrivacyInfo.xcprivacy`.
4. StoreKit/In-App Purchase design after commercial-compliance review (purchases
   intentionally disabled).
5. App Store metadata, screenshots, age rating, export-compliance answers.
6. Signed physical-device E2E: Google/Apple login, Agent SSE, Plaid Link, IBKR,
   APNs rotation, notification tap routing.

## Upgrades applied in this pass

1. Push device un-registration now uses the same environment as registration
   (sandbox in Debug, production in Release) instead of hardcoding `"production"`,
   and is invoked on **account deletion** as well as logout so no stale APNs device
   row is left behind.
2. `AgentView` error strip refactored into an explicit `showsRetry(for:)` switch
   (no retry for `.forbidden`/`.paymentRequired`) so the retry visibility rule is
   auditable.
3. Login flow clears the prior error message before each new Google/Apple attempt,
   so stale failures no longer linger during retries.
4. Account gains an About section showing `CFBundleShortVersionString (build)` for
   support triage, with English and Simplified Chinese strings added.
5. `KeychainTokenStore` now explicitly opts into the data-protection keychain
   (`kSecUseDataProtectionKeychain`), centralizes its query dictionary, keeps
   `kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`, and accepts a configurable
   `service`/`account` so tests never touch the production keychain item.
6. `PGTheme` accent-text contrast documented in Findings for future use.

## Upgrades applied in this pass (wave 2 — reliability & testability)

7. **Centralized retry/backoff in `APIClient`**: idempotent requests (GET/PUT/
   DELETE) retry transient transport failures and 5xx up to twice with 0.5 s / 1 s
   backoff; POST (incl. SSE stream) never auto-retries. Failures are logged to
   `os.Logger`.
8. **`X-PG-Locale` header now follows the in-app language selection** (from the
   `app.language` preference) instead of `Locale.current`, so server responses
   match what the user actually chose, not the device locale.
9. **Cold-start `puregamma://` deep links are gated by host/path** — only
   `puregamma://oauth/callback` and `puregamma://oauth/ibkr` can resume a pending
   OAuth exchange.
10. **Agent SSE state machine extracted into a pure `AgentStreamReducer`** — the
    delta/citation/tool/completed/failed/canceled transitions are now a
    unit-testable struct; `AgentViewModel` mirrors reducer state and preserves the
    prior behavior when the visible message disappears mid-stream.
11. **New test coverage** (16 tests added):
    - `APIClientErrorTests` (6): 401/402/403/429 mapping, FastAPI validation-array
      message extraction, Retry-After parsing, GET transport retry, POST no-retry —
      via an injected mock `URLProtocol` session.
    - `AgentStreamReducerTests` (7): runID capture, delta accumulation, citation
      deduplication, tool activity, completed/failed/canceled transitions.
    - `KeychainTokenStoreTests` (3): lifecycle round-trip, overwrite, idempotent
      delete — against isolated test-only keychain services.

## Upgrades applied in this pass (wave 3 — external review fixes)

13. **`AppLinks` no longer crashes on misconfiguration.** Privacy/Terms/Support
    URLs are now optional; missing or malformed build-config values hide the
    footer links instead of `fatalError` at launch on the Sign-in screen. The
    API base URL keeps its hard guard because an endpoint-less Release build is
    unusable.
14. **`AgentStreamReducer.toolCompleted` now removes entries by exact match**
    (`"RUNNING · \(tool)"` / `"DONE · \(tool)"`) instead of substring
    `contains`, so completing a tool can never clear an unrelated
    `news_research`-style entry and a repeated completion cannot duplicate
    DONE entries.
15. **`APIClient.stream` now sends `X-PG-Locale`** like `request`, so streaming
    endpoints observe the in-app language instead of silently falling back to
    the device locale.
16. **Post-stream reload flash removed.** `recoverConversation` reloads from the
    server only when reconciliation is needed (streaming/failed/canceled last
    message or no loaded rows); a locally complete run is kept as-is.
17. **Attachment size is checked before reading the file** (`fileSizeKey`
    resource value short-circuits the 20 KB/50 KB caps), avoiding a large
    allocation for oversized picks.
18. **Plaid Link and IBKR OAuth continuations now have a 300 s safety timeout**
    with a single-resume guard, so a never-settling session can no longer leave
    the button busy forever.
19. **Removed the dead trailing `throw` in `APIClient.request`** by
    restructuring the retry loop to `while true` with an explicit attempt
    counter.
20. **`TodayViewModel` empty detection is now concrete** — `isEmpty:` closures
    on the typed values replace the `as? any Collection` runtime-cast hack.
21. **SSE parser tolerates CRLF line endings** defensively.
22. **New tests (8 added):** SSE multi-line data join, comment lines, default
    event name, CRLF tolerance, state reset between events; reducer tool-
    completion idempotency/exactness; `onUnauthorized` side-effect invocation.

## Upgrades applied in this pass (wave 4 — UI review fixes)

23. **Deleted the dead `StaleBanner` component** (`PGTheme.swift`); the stale
    surface is now exclusively `StaleDataBanner`, which labels cached data with
    its saved timestamp. Removed its orphaned zh-Hans keys
    (`"Data may be stale · %@"`, `"Attachment must be UTF-8 text and no larger
    than 20 KB."` — the latter never matched any code).
24. **Today metrics adapt to Dynamic Type.** At Accessibility sizes the
    PLAN/CREDITS/STATUS row stacks vertically so monospaced headline values get
    full width instead of hard-truncating in three narrow columns.
25. **Portfolio NAV value cannot overflow the badge row** — `lineLimit(1)` +
    `minimumScaleFactor(0.5)` + flexible leading frame.
26. **NAVChart keeps its crosshair tooltip after touch-up**, so values can be
    read without holding a finger on the chart.
27. **Accessibility labels are now localized.** `MarketRow` and
    `StaleDataBanner` labels go through `String(localized:)` (derived keys
    `"%@, %@, change %@, source %@"` and `"Stale data saved %@"`), so Chinese
    VoiceOver users hear the translated text; the matching zh-Hans keys were
    added/aligned. Previously the labels were raw English interpolations and
    the zh translation for the market row was silently ineffective.

## Recommended next PR (beyond code, order matters)

1. Apply the signing/credentials gates and run the signed physical-device E2E
   checklist.
2. Token refresh flow: blocked on a backend `/auth/mobile/refresh` endpoint
   (mobile auth currently issues access tokens directly; no refresh grant exists).
3. Server-side upstream reliability and stale-data alerting remain the top
   external risk for release.
