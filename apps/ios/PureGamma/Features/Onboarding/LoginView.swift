import AuthenticationServices
import SwiftUI

struct LoginView: View {
    @Environment(AppState.self) private var app
    @State private var error: String?
    @State private var appleNonce = ""
    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            Spacer()
            HStack(spacing: 12) { Text("PΓ").font(.headline.monospaced()).frame(width: 42, height: 42).overlay(Rectangle().stroke(.primary)); Text("PUREGAMMA AI").font(.headline.monospaced()).tracking(1) }
            Text("Market intelligence,\nwith clear boundaries.").font(.largeTitle.weight(.semibold)).tracking(-1)
            Text("Research, options and portfolio context for secondary-market investors.").foregroundStyle(.secondary)
            if let error { Label(error, systemImage: "exclamationmark.triangle").font(.footnote).foregroundStyle(PGTheme.negative) }
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
            Button { Task { do { app.completeLogin(try await app.authentication.signInWithGoogle()) } catch APIError.canceled { self.error = nil } catch { self.error = error.localizedDescription } } } label: {
                HStack { Image(systemName: "safari"); Text("Continue securely with Google"); Spacer(); if app.authentication.isSigningIn { ProgressView() } else { Image(systemName: "arrow.up.right") } }.frame(maxWidth: .infinity).padding(.vertical, 8)
            }.buttonStyle(.borderedProminent).tint(PGTheme.accent).foregroundStyle(.black).disabled(app.authentication.isSigningIn).accessibilityIdentifier("google-sign-in").accessibilityHint("Opens Google sign in in a secure system browser")
            HStack(spacing: 18) {
                Link("Privacy", destination: AppLinks.privacyPolicy)
                Link("Terms", destination: AppLinks.terms)
                Link("Support", destination: AppLinks.support)
            }.font(.caption).foregroundStyle(.secondary).accessibilityElement(children: .contain)
            RiskDisclosureView(); Spacer().frame(height: 30)
        }.padding(24).background(Color(uiColor: .systemBackground))
    }

    private func signInWithApple(_ result: Result<ASAuthorization, Error>) async {
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
