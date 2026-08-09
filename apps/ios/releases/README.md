# PureGamma iOS release packages

Versioned, signed IPAs produced by `scripts/ios-build-release.sh` on a Mac.

| File | What it is |
| --- | --- |
| `PureGamma-<version>-<build>-app-store.ipa` | App Store / TestFlight upload |
| `PureGamma-<version>-<build>-ad-hoc.ipa` | Registered-device install without App Store |
| `PureGamma-<version>-<build>-development.ipa` | Development provisioning install |

This folder mirrors `apps/android/releases/` (versioned APKs) and the web
deployment flow (`deploy/deploy.sh`): every release is a versioned artifact
that can be rebuilt from the same commit.

## Produce a package (macOS only)

Apple requires Xcode + an Apple Developer account; iOS binaries cannot be
built on Windows/Linux.

```bash
# macOS, repository root
bash scripts/ios-build-release.sh info          # current version state
bash scripts/ios-build-release.sh bump          # bump build number (CURRENT_PROJECT_VERSION)
bash scripts/ios-build-release.sh app-store     # signed IPA for App Store / TestFlight
bash scripts/ios-build-release.sh ad-hoc        # signed IPA for registered devices
```

Prerequisites:

1. `Config/Local.xcconfig` with `PUREGAMMA_DEVELOPMENT_TEAM = <Team ID>`
   (kept out of version control via `apps/ios/.gitignore`).
2. Xcode project signing set to Automatic with valid provisioning profiles.
3. Push entitlement (`aps-environment`) configured for the target environment.

## Upload to TestFlight

```bash
xcrun altool --upload-app -f apps/ios/releases/PureGamma-1.0.0-1-app-store.ipa \
  -t ios --apiKey <KEY_ID> --apiIssuer <ISSUER_ID>
```

## Release gates before first upload

- Apple Team + Sign in with Apple + APNs push entitlement registered for
  `ai.puregamma.ios`.
- Production HTTPS mobile Google OAuth callback registered
  (`MOBILE_GOOGLE_OAUTH_REDIRECT_URI`, `MOBILE_OAUTH_REDIRECT_URIS`).
- Server-only `APPLE_*` / `APNS_*` credentials configured on the API.
- `/privacy` and `/terms` live at `puregamma.ai`; App Store privacy
  disclosures match `PrivacyInfo.xcprivacy`.
- Signed physical-device E2E passed (login, Agent SSE, Plaid, IBKR, APNs).
