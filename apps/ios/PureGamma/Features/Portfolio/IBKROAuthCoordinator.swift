import AuthenticationServices
import UIKit

@MainActor
final class IBKROAuthCoordinator: NSObject, ASWebAuthenticationPresentationContextProviding {
    private static let timeout: TimeInterval = 300

    private final class SessionBox {
        var completed = false

        func finish(_ action: () -> Void) {
            guard !completed else { return }
            completed = true
            action()
        }
    }

    private var session: ASWebAuthenticationSession?

    func connect(repository: PortfolioRepository) async throws -> Portfolio {
        let configuration = repository.client.configuration
        let authorizationURL = try await repository.ibkrMobileURL(redirectURI: configuration.portfolioCallbackURL)
        let callback = try await withCheckedThrowingContinuation { continuation in
            let box = SessionBox()
            let session = ASWebAuthenticationSession(url: authorizationURL, callbackURLScheme: configuration.callbackScheme) { url, error in
                box.finish {
                    if let url { continuation.resume(returning: url) }
                    else { continuation.resume(throwing: error ?? APIError.canceled) }
                }
            }
            session.presentationContextProvider = self
            session.prefersEphemeralWebBrowserSession = false
            self.session = session
            if !session.start() {
                self.session = nil
                box.finish { continuation.resume(throwing: APIError.transport("Unable to start secure browser session")) }
            }
            // Safety net: if the system browser handoff never settles, the UI
            // must not stay busy forever. `box` guarantees a single resume.
            Task {
                try? await Task.sleep(for: .seconds(Self.timeout))
                box.finish {
                    self.session = nil
                    continuation.resume(throwing: APIError.transport(String(localized: "OAuth session timed out. Please try again.")))
                }
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
