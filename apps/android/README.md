# PureGamma Android

Android client for the production PureGamma platform. Native Android owns secure
Google sign-in, secure token storage and microphone permission; after sign-in it
opens the production web product inside an authenticated WebView. This keeps the
Android UI and features aligned with the website, including Billing, Credits,
Skills, Portfolio, Autopilot and Private Secretary voice conversations.

## Open and run

Open `apps/android` in Android Studio. The project requires Android Studio with
JDK 17 or newer and Android SDK 36.1. Debug and release builds use the production
API by default:

```text
https://api.puregamma.ai
```

For a separate HTTPS development API, pass a Gradle property when building:

```powershell
.\gradlew.bat assembleDebug -PPG_API_BASE_URL=https://api-dev.example.com
```

Build and test from the `apps/android` directory:

```powershell
.\gradlew.bat testDebugUnitTest assembleDebug
```

The debug APK is generated at `app/build/outputs/apk/debug/app-debug.apk`.

## Release build

Release builds require a persistent upload/signing key. Keep the key and its
password outside Git, then provide them only in the release shell:

```powershell
$env:PG_KEYSTORE_FILE = 'C:\secure\puregamma-android-release.jks'
$env:PG_KEYSTORE_PASSWORD = '...'
$env:PG_KEY_ALIAS = 'puregamma-release'
$env:PG_KEY_PASSWORD = '...'
.\gradlew.bat bundleRelease assembleRelease
```

The signed artifacts are written to `app/build/outputs/bundle/release/` and
`app/build/outputs/apk/release/`. The same signing key must be retained for all
future updates.

## Mobile OAuth

Google sign-in uses the existing FastAPI mobile OAuth endpoints and callback:

```text
POST /auth/mobile/google/start
GET  /auth/mobile/google/callback
POST /auth/mobile/google/exchange
puregamma://oauth/callback
```

The app generates a per-login state, nonce and PKCE verifier. The browser only
returns a one-time exchange code. The Google client secret and provider tokens
remain on the server. Ensure `puregamma://oauth/callback` is included in the API
server's `MOBILE_OAUTH_REDIRECT_URIS` setting.

## Security and product boundaries

- The API bearer token is encrypted with an AES-GCM key held by Android Keystore.
- Production networking is HTTPS-only and cleartext traffic is disabled.
- No Stripe, Plaid, Moralis, IBKR, exchange, wallet, model or TTS secret is in the APK.
- Portfolio connections are read-only. The Android client contains no order,
  transfer, withdrawal, seed phrase or private-key flow.
- Autopilot exposes research review only and never represents live execution.
- API failures are shown explicitly; the client does not substitute mock market,
  report or portfolio data.

## Product surface

- Full authenticated PureGamma web product in the Android app, with one source of
  truth for subscription badges, Credits, reports, Skills and portfolio data.
- Private Secretary supports the website's voice conversation UI. Android requests
  microphone consent at the OS level and only grants WebView audio capture after
  the user approves it.
- External payment and institution authorization flows use the system browser;
  product session cookies remain HttpOnly and are never injected into JavaScript.
