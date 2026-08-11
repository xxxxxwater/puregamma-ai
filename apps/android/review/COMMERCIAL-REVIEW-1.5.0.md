# PureGamma Android — Commercial Review & Upgrade (1.5.0)

Date: 2026-08-05. Review scope: entire `apps/android` client. Goal: commercial
grade (release-safety, security, reliability, i18n, legal surface).

## Critical issues found and fixed

1. **Release builds broke Gson deserialization (R8).** `minifyEnabled` with no
   keep rules meant R8 could rename/strip DTO and cached-model fields, silently
   nulling every API response in release APKs.
   → `proguard-rules.pro` now keeps `data.remote.dto.**` and `model.**` (fields
   verified present in `app-release-unsigned.apk` via dexdump).
2. **401 handling corrupted responses.** `AuthErrorInterceptor` called
   `response.close()` before Retrofit/SseClient read the body, surfacing
   `IllegalStateException: closed` instead of a clean sign-out.
   → Interceptor now passes the response through untouched and fires the
   sign-out exactly once (`AtomicBoolean`).
3. **Raw server errors reached users.** Retrofit `HttpException` bodies were
   never parsed, so users saw "HTTP 500" instead of friendly messages.
   → New `ApiErrorInterceptor` parses FastAPI `detail.{code,message,reason}`
   into `RetrofitApiException` for every call. Interceptor order fixed so the
   401 handler sees responses before the error parser throws.

## High-priority findings fixed

4. **Declared deep links were dead.** `puregamma://plaid/callback` and
   `puregamma://oauth/ibkr` intent filters existed but every callback showed a
   bogus "Google sign-in failed" error. Backend routes were complete.
   → `AppViewModel.handleDeepLink` routes Google/IBKR/Plaid callbacks; new
   `beginPlaidLink` / `beginIbkrOAuth` flows wired into the Portfolio screen
   (Plaid Link custom tab → public token exchange; IBKR start → code complete).
   Connection rows gained a remove (delete) action.
5. **Dead/legacy code removed** (attack surface + APK size):
   `core/ApiClient`, `core/SecureTokenStore`, `core/ErrorMessages`,
   `core/MobileOAuth` (WebView-era duplicates), `ui/WebProductScreen`,
   `CachedTodayRepository`, `PlaidLinkCoordinator`, `IbkrOAuthCoordinator`,
   fake push stubs `PureGammaMessagingService` + `PureGammaPushBridge`
   (backend has no Android push path — APNS only) and their manifest entries.
   `RECORD_AUDIO`/`MODIFY_AUDIO_SETTINGS` removed (no WebView consumer left).
6. **NavHistoryChart duplicated range labels** for every unselected range.
   → Single `Text` per range with selected background + click handler.
7. **~30 hardcoded UI strings** (RUNNING/READY, section subtitles, connect
   buttons, legal) → extracted to `values/strings.xml` and
   `values-zh-rCN/strings.xml`.

## Hardening applied

8. Session bootstrap distinguishes auth failure (401 → sign out) from network
   failure (retryable `sessionError` + retry button); clients recreated per
   login so the 401 dedupe re-arms; `forceSignOut` clears every screen state.
9. `SecureTokenStore`: blank-token guard, save wrapped in `runCatching`,
   corrupt-ciphertext auto-clears; GCM `RandomizedEncryptionRequired` set.
10. Manifest: `enableOnBackInvokedCallback`, `network_security_config.xml`
    (cleartext off, system CAs), fake FCM metadata removed.
11. Account screen: Terms of Service / Privacy Policy links (web legal pages)
    and version display; login screen links the same legal pages.
12. Streaming errors now attach to the assistant message with a friendly
    message instead of a raw global toast.

## Validation

- `.\gradlew.bat testDebugUnitTest assembleDebug` — all unit tests pass
  (existing OAuth/error/SSE tests + new `ApiErrorInterceptorTest` with
  MockWebServer covering structured, plain-detail, reason-fallback and
  non-JSON errors).
- `.\gradlew.bat assembleRelease` — R8 + lintVital pass; DTO/model classes
  confirmed present in the release APK.
- Version bumped to 1.5.0 (versionCode 9).

## Remaining commercial items (documented, not blocking)

- Real push notifications require an FCM project + `google-services.json`;
  server-side Android delivery does not exist yet.
- Certificate pinning is deliberately not enabled (system CAs + HTTPS-only);
  revisit if the API adds a dedicated mobile domain.
- App signing key must be kept and supplied via `PG_KEYSTORE_*` env vars.
- Play Store listing assets (screenshots, privacy policy link) are out of repo.
