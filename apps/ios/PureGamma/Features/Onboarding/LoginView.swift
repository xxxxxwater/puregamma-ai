import AuthenticationServices
import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var app
    @State private var error: String?
    @State private var appleNonce = ""
    @State private var email = ""
    @State private var password = ""
    @State private var displayName = ""
    @State private var isRegistering = false
    @FocusState private var focusedField: Field?
    private enum Field: Hashable { case email, password, displayName }

    private var canSubmitEmail: Bool {
        guard !email.isEmpty, !password.isEmpty else { return false }
        if isRegistering, password.count < 8 { return false }
        return true
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Spacer()
            HStack(spacing: 12) { Text("PΓ").font(.headline.monospaced()).frame(width: 42, height: 42).overlay(Rectangle().stroke(.primary)); Text("PUREGAMMA AI").font(.headline.monospaced()).tracking(1) }
            Text("Market intelligence,\nwith clear boundaries.").font(.largeTitle.weight(.semibold)).tracking(-1)
            Text("Research, options and portfolio context for secondary-market investors.").foregroundStyle(.secondary)
            if let error { Label(error, systemImage: "exclamationmark.triangle").font(.footnote).foregroundStyle(PGTheme.negative) }
            VStack(alignment: .leading, spacing: 10) {
                Text(isRegistering ? "Create account" : "Email sign in").font(.headline)
                TextField("Email", text: $email)
                    .textContentType(.emailAddress)
                    .keyboardType(.emailAddress)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .focused($focusedField, equals: .email)
                    .submitLabel(.next)
                    .onSubmit { focusedField = isRegistering ? .displayName : .password }
                    .accessibilityIdentifier("email-field")
                if isRegistering {
                    TextField("Name (optional)", text: $displayName)
                        .textContentType(.name)
                        .focused($focusedField, equals: .displayName)
                        .submitLabel(.next)
                        .onSubmit { focusedField = .password }
                        .accessibilityIdentifier("display-name-field")
                }
                SecureField("Password", text: $password)
                    .textContentType(isRegistering ? .newPassword : .password)
                    .focused($focusedField, equals: .password)
                    .submitLabel(.go)
                    .onSubmit { if canSubmitEmail { submitEmailForm() } }
                    .accessibilityIdentifier("password-field")
                Button { submitEmailForm() } label: {
                    HStack { Text(isRegistering ? "Create account" : "Sign in"); Spacer(); if app.authentication.isSigningIn { ProgressView() } else { Image(systemName: "arrow.right") } }
                        .frame(maxWidth: .infinity).padding(.vertical, 8)
                }
                .buttonStyle(.bordered).tint(PGTheme.accent).disabled(!canSubmitEmail || app.authentication.isSigningIn)
                .accessibilityIdentifier("email-submit")
                Button(isRegistering ? "Already have an account? Sign in" : "New here? Create an account") { withAnimation(.easeInOut(duration: 0.2)) { isRegistering.toggle(); error = nil; focusedField = .email } }
                    .font(.footnote).foregroundStyle(.secondary).accessibilityIdentifier("email-mode-toggle")
            }
            .textFieldStyle(.roundedBorder)
            Divider()
            SignInWithAppleButton(.continue) { request in
                appleNonce = PKCE.random()
                request.requestedScopes = [.fullName, .email]
                request.nonce = PKCE.appleNonce(for: appleNonce)
            } onCompletion: { result in
                Task { await signInWithApple(result) }
            }
            .signInWithAppleButtonStyle(.whiteOutline)
            .frame(height: 50)
            .disabled(app.authentication.isSigningIn)
            .accessibilityIdentifier("apple-sign-in")
            .accessibilityHint("Creates or signs in to your PureGamma account with Apple")
            Button { Task { error = nil; do { app.completeLogin(try await app.authentication.signInWithGoogle()) } catch APIError.canceled { self.error = nil } catch { self.error = error.localizedDescription } } } label: {
                HStack { Image(systemName: "safari"); Text("Continue securely with Google"); Spacer(); if app.authentication.isSigningIn { ProgressView() } else { Image(systemName: "arrow.up.right") } }.frame(maxWidth: .infinity).padding(.vertical, 8)
            }.buttonStyle(.borderedProminent).tint(PGTheme.accent).foregroundStyle(PGTheme.onAccent).disabled(app.authentication.isSigningIn).accessibilityIdentifier("google-sign-in").accessibilityHint("Opens Google sign in in a secure system browser")
            HStack(spacing: 18) {
                if let url = AppLinks.privacyPolicy { Link("Privacy", destination: url) }
                if let url = AppLinks.terms { Link("Terms", destination: url) }
                if let url = AppLinks.support { Link("Support", destination: url) }
            }.font(.caption).foregroundStyle(.secondary).accessibilityElement(children: .contain)
            RiskDisclosureView(); Spacer().frame(height: 30)
        }.padding(24).background(Color(uiColor: .systemBackground))
    }

    private func submitEmailForm() {
        error = nil
        Task {
            do {
                let user = try isRegistering
                    ? await app.authentication.registerWithEmail(email: email, password: password, name: displayName)
                    : await app.authentication.signInWithEmail(email: email, password: password)
                app.completeLogin(user)
            } catch APIError.canceled { error = nil }
            catch { self.error = emailErrorMessage(error) }
        }
    }

    private func emailErrorMessage(_ error: Error) -> String {
        switch error.localizedDescription {
        case "INVALID_CREDENTIALS": String(localized: "Incorrect email or password.")
        case "EMAIL_NOT_VERIFIED": String(localized: "This email is not verified yet. Check your inbox for the verification link.")
        case "EMAIL_ALREADY_REGISTERED": String(localized: "An account with this email already exists. Sign in instead.")
        case "PASSWORD_TOO_WEAK": String(localized: "Password must be at least 8 characters with a letter, a digit and an uppercase letter.")
        case "INVALID_EMAIL": String(localized: "Enter a valid email address.")
        case "RATE_LIMITED": String(localized: "Too many attempts. Try again in 15 minutes.")
        default: error.localizedDescription
        }
    }

    private func signInWithApple(_ result: Result<ASAuthorization, Error>) async {
        error = nil
        do {
            let authorization: ASAuthorization
            switch result {
            case .success(let value): authorization = value
            case .failure(let value as ASAuthorizationError) where value.code == .canceled: throw APIError.canceled
            case .failure(let value): throw value
            }
            guard let credential = authorization.credential as? ASAuthorizationAppleIDCredential,
                  !appleNonce.isEmpty else { throw APIError.invalidRequest }
            app.completeLogin(try await app.authentication.completeAppleSignIn(credential: credential, rawNonce: appleNonce))
            appleNonce = ""
            error = nil
        }
        catch APIError.canceled { error = nil }
        catch { self.error = error.localizedDescription }
    }
}
