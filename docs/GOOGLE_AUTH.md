# Google Authentication

## Flow

PureGamma uses the existing project JWT/session system with Google OpenID Connect authorization code flow. It requests only `openid email profile`.

1. The API creates state, nonce, and a PKCE verifier in short-lived HttpOnly SameSite=Lax cookies.
2. Google receives a SHA-256 PKCE challenge and nonce.
3. The callback verifies state, exchanges the code with the exact redirect URI and verifier, then verifies the Google ID token signature, issuer, audience, expiration, nonce, and verified-email claim.
4. `provider=google` plus Google `sub` identifies the external identity. Email is used only for a verified-email account-link policy.
5. The API creates or updates `user_identities`, updates verification/login timestamps, rotates the session version, and sets the project JWT in an HttpOnly cookie.

Google access and refresh tokens are not persisted and are not used to call other Google APIs.

## Configuration

Create a Google OAuth Web application and configure the exact local callback, for example:

```env
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
GOOGLE_REDIRECT_URI=http://localhost:3000/zh/auth/google/callback
SESSION_SECRET=use-a-long-random-secret
```

Add both localized callback URLs if users can start auth on both locales. Production uses HTTPS and `APP_ENV=production`, which enables the Secure session cookie.

## Session behavior

Browser requests use `credentials: include`; no auth token is written to localStorage. Bearer JWT remains supported for non-browser API clients. Login rotates `session_version`; logout increments it again, invalidating prior cookies.
