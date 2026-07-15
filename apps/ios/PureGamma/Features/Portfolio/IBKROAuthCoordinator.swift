import AuthenticationServices
import UIKit

@MainActor
final class IBKROAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private var session: ASWebAuthenticationSession?

    func connect(repository: PortfolioRepository) async throws -> Portfolio {
        let configuration = repository.client.configuration
        let authorizationURL = try await repository.ibkrMobileURL(redirectURI: configuration.portfolioCallbackURL)
        let callback = try await withCheckedThrowingContinuation { continuation in
            let session = ASWebAuthenticationSession(url: authorizationURL, callbackURLScheme: configuration.callbackScheme) { url, error in
                if let url { continuation.resume(returning: url) }
                else { continuation.resume(throwing: error ?? APIError.canceled) }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            self.session = session
            if !session.start() {
                self.session = nil
                continuation.resume(throwing: APIError.transport("Unable to start secure browser session"))
            }
        }
        session = nil
        guard callback.scheme == configuration.callbackScheme,
              callback.host == "oauth",
              callback.path == "/ibkr" else { throw APIError.forbidden(String(localized: "OAuth callback verification failed")) }
        let items = URLComponents(url: callback, resolvingAgainstBaseURL: false)?.queryItems ?? []
        if items.contains(where: { $0.name == "error" }) { throw APIError.canceled }
        guard let code = items.first(where: { $0.name == "code" })?.value else { throw APIError.invalidRequest }
        return try await repository.completeIBKR(code: code)
    }

    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        UIApplication.shared.connectedScenes
            .compactMap { ($0 as? UIWindowScene)?.keyWindow }
            .first ?? ASPresentationAnchor()
    }
}
