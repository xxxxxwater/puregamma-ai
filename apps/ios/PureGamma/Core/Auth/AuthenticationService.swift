import AuthenticationServices
import Foundation
import Observation
import UIKit

@MainActor @Observable
final class AuthenticationService: NSObject, ASWebAuthenticationPresentationContextProviding {
    @ObservationIgnored
    private let client: APIClient
    @ObservationIgnored
    private let tokenStore: TokenStoring
    @ObservationIgnored
    private var webSession: ASWebAuthenticationSession?
    @ObservationIgnored
    private var verifier = ""
    @ObservationIgnored
    private var nonce = ""
    @ObservationIgnored
    private var state = ""
    @ObservationIgnored
    private var callbackContinuation: CheckedContinuation<URL, Error>?
    var isSigningIn = false

    init(client: APIClient, tokenStore: TokenStoring) { self.client = client; self.tokenStore = tokenStore }
    var hasToken: Bool { tokenStore.read() != nil }

    func signInWithGoogle() async throws -> User {
        isSigningIn = true; defer { isSigningIn = false }
        verifier = PKCE.random(byteCount: 48); nonce = PKCE.random(); state = PKCE.random()
        let payload = MobileOAuthStartDTO(redirectURI: client.configuration.callbackURL, codeChallenge: PKCE.challenge(for: verifier), clientState: state, nonce: nonce)
        let start: MobileOAuthStartResponseDTO = try await client.request("/auth/mobile/google/start", method: "POST", body: payload)
        guard let authURL = URL(string: start.authURL) else { throw APIError.invalidRequest }
        let callback = try await withCheckedThrowingContinuation { continuation in
            callbackContinuation = continuation
            let session = ASWebAuthenticationSession(url: authURL, callbackURLScheme: client.configuration.callbackScheme) { [weak self] url, error in
                guard let self else { return }
                if let url { self.resolveCallback(url) } else { self.rejectCallback(error ?? APIError.canceled) }
            }
            session.presentationContextProvider = self; session.prefersEphemeralWebBrowserSession = false; webSession = session
            if !session.start() { rejectCallback(APIError.transport("Unable to start secure browser session")) }
        }
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        let value: (String) -> String? = { name in items.first(where: { $0.name == name })?.value }
        guard value("state") == state else { throw APIError.forbidden(String(localized: "OAuth state verification failed")) }
        if value("error") != nil { throw APIError.canceled }
        guard let code = value("code") else { throw APIError.invalidRequest }
        let exchange: MobileOAuthExchangeResponseDTO = try await client.request("/auth/mobile/google/exchange", method: "POST", body: MobileOAuthExchangeDTO(code: code, codeVerifier: verifier, nonce: nonce))
        try tokenStore.save(exchange.accessToken)
        return exchange.user.domain
    }

    func completeAppleSignIn(credential: ASAuthorizationAppleIDCredential, rawNonce: String) async throws -> User {
        isSigningIn = true; defer { isSigningIn = false }
        guard let identityData = credential.identityToken,
              let identityToken = String(data: identityData, encoding: .utf8),
              let codeData = credential.authorizationCode,
              let authorizationCode = String(data: codeData, encoding: .utf8) else {
            throw APIError.decoding(String(localized: "Apple did not return the required identity credentials."))
        }
        let exchange: MobileOAuthExchangeResponseDTO = try await client.request(
            "/auth/mobile/apple/exchange",
            method: "POST",
            body: AppleOAuthExchangeDTO(
                identityToken: identityToken,
                authorizationCode: authorizationCode,
                nonce: rawNonce,
                givenName: credential.fullName?.givenName,
                familyName: credential.fullName?.familyName
            )
        )
        try tokenStore.save(exchange.accessToken)
        return exchange.user.domain
    }

    func handleCallbackURL(_ url: URL) { guard url.scheme == client.configuration.callbackScheme else { return }; resolveCallback(url) }
    private func resolveCallback(_ url: URL) { callbackContinuation?.resume(returning: url); callbackContinuation = nil; webSession = nil }
    private func rejectCallback(_ error: Error) { callbackContinuation?.resume(throwing: error); callbackContinuation = nil; webSession = nil }
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { ($0 as? UIWindowScene)?.keyWindow }
            .first ?? ASPresentationAnchor()
    }

    func currentUser() async throws -> User { let value: UserEnvelopeDTO = try await client.request("/me"); return value.user.domain }
    func clearLocalSession() { tokenStore.delete() }
    func logout() async { let _: EmptyResponseDTO? = try? await client.request("/auth/logout", method: "POST"); clearLocalSession() }
}
