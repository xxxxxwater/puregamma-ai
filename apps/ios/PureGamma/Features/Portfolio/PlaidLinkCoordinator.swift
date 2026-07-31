import Foundation
import LinkKit
import UIKit

@MainActor
enum PlaidLinkCoordinator {
    private final class SessionBox {
        var session: PlaidLinkSession?
        var completed = false

        func finish(_ action: () -> Void) {
            guard !completed else { return }
            completed = true
            action()
            session = nil
        }
    }

    static func open(token: String) async throws -> (publicToken: String, institution: String) {
        try await withCheckedThrowingContinuation { continuation in
            let box = SessionBox()
            let configuration = LinkTokenConfiguration(
                token: token,
                onSuccess: { success in
                    box.finish {
                        continuation.resume(returning: (success.publicToken, success.metadata.institution.name))
                    }
                },
                onExit: { exit in
                    box.finish {
                        continuation.resume(throwing: exit.error ?? APIError.canceled)
                    }
                },
                onEvent: { _ in },
                onLoad: { }
            )
            do {
                let session = try Plaid.createPlaidLinkSession(configuration: configuration)
                box.session = session
                guard let controller = UIApplication.shared.connectedScenes.compactMap({ ($0 as? UIWindowScene)?.keyWindow?.rootViewController }).first else {
                    box.finish { continuation.resume(throwing: APIError.invalidRequest) }
                    return
                }
                session.open(using: .viewController(controller))
            } catch {
                box.finish { continuation.resume(throwing: error) }
            }
        }
    }
}
