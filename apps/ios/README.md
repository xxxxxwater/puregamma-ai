# PureGamma iOS

Production-oriented native client for the existing PureGamma FastAPI platform.

## Open and run

Open `PureGamma.xcodeproj` in Xcode 26 or newer. Copy
`Config/Local.xcconfig.example` to `Config/Local.xcconfig`, enter the Apple
Development Team identifier shown in Xcode, select the `PureGamma` scheme and a
paired iPhone running iOS 17+. The project uses Swift 6 and the official Plaid
LinkKit package (`plaid-link-ios` 7.0.3+).

Debug uses `http://127.0.0.1:8000` and a development-only local-network transport
exception. For a physical iPhone, set the scheme environment variable
`PUREGAMMA_API_BASE_URL` to an HTTPS development endpoint or a reachable local
API address. Release is fixed to `https://api.puregamma.ai`, requires HTTPS and
contains no insecure transport exception. Start the development API from the
repository root:

```bash
uvicorn apps.api.main:app --reload --host 127.0.0.1 --port 8000
```

For device OAuth, configure the server:

```env
MOBILE_GOOGLE_OAUTH_REDIRECT_URI=https://api.example.com/auth/mobile/google/callback
MOBILE_OAUTH_REDIRECT_URIS=puregamma://oauth/callback
APPLE_CLIENT_ID=ai.puregamma.ios
APPLE_TEAM_ID=<Apple Developer Team ID>
APPLE_KEY_ID=<Sign in with Apple key ID>
APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
MOBILE_IBKR_OAUTH_REDIRECT_URI=https://api.example.com/portfolio/ibkr/mobile/callback
MOBILE_PORTFOLIO_REDIRECT_URIS=puregamma://oauth/ibkr
APNS_ENABLED=true
APNS_TEAM_ID=<Apple Developer Team ID>
APNS_KEY_ID=<APNs key ID>
APNS_BUNDLE_ID=ai.puregamma.ios
APNS_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
```

Register the HTTPS callback in Google Cloud. The app custom URL receives only a
single-use code; the Google secret and provider tokens remain server-side.
Enable Sign in with Apple for the bundle identifier in Apple Developer. The
Apple `.p8` private key is server-only and must never be placed in this project.
Register the mobile IBKR HTTPS callback with IBKR. Its provider code is exchanged
by FastAPI and the app receives only a short-lived, single-use completion code.
APNs device tokens are encrypted at rest by the API; the APNs `.p8` key remains
server-only.

## Security and product boundaries

- Bearer tokens are stored only in Keychain.
- Sign in with Apple uses a hashed nonce; Google mobile OAuth uses state, nonce,
  PKCE and a one-time exchange code.
- Account deletion requires re-entering the signed-in email. The API revokes
  the stored Apple refresh token and removes server-owned account data.
- No Stripe, LLM, Plaid, IBKR, exchange secret, private key or seed phrase is in
  the app.
- Billing is read-only pending App Store compliance review; web Stripe Checkout
  is not exposed as an in-app purchase path.
- Portfolio Autopilot is research-only. LIVE orders, transfers, withdrawals and
  wallet signing are absent.
- API failures render explicit unavailable/offline/permission states. The app
  never substitutes mock balances, prices or reports.
- Previously returned market, report and portfolio responses may be shown only
  as clearly labelled stale data. The file-protected cache is cleared on 401,
  logout and account deletion.

## Device build and tests

```bash
xcodebuild build -project apps/ios/PureGamma.xcodeproj \
  -scheme PureGamma -destination 'generic/platform=iOS'

xcodebuild build-for-testing -project apps/ios/PureGamma.xcodeproj \
  -scheme PureGamma -destination 'generic/platform=iOS'
```

Run unit, UI, Dynamic Type and accessibility tests from Xcode after selecting a
paired iPhone and development team. Backend mobile-auth and deletion tests are
in `tests/test_mobile_auth.py` and
`tests/test_apple_auth_and_account_deletion.py`. See `DELIVERY_REPORT.md` for
current validation and release blockers.
