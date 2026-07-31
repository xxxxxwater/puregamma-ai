import Foundation

enum APIError: LocalizedError, Equatable {
    case invalidRequest, transport(String), unauthorized, paymentRequired(String), forbidden(String), rateLimited(retryAfter: Int?), unavailable(String), server(status: Int, message: String), decoding(String), canceled

    var errorDescription: String? {
        switch self {
        case .invalidRequest: String(localized: "Invalid request")
        case .transport: String(localized: "You appear to be offline. Check your connection and retry.")
        case .unauthorized: String(localized: "Your session expired. Please sign in again.")
        case .paymentRequired(let message), .forbidden(let message), .unavailable(let message), .server(_, let message): message
        case .rateLimited(let seconds): seconds.map { String(localized: "Too many requests. Retry in \($0) seconds.") } ?? String(localized: "Too many requests. Please retry later.")
        case .decoding: String(localized: "The server returned an unsupported response.")
        case .canceled: String(localized: "Canceled")
        }
    }

    var presentation: LoadFailure {
        switch self {
        case .transport: .offline
        case .forbidden: .permissionDenied
        case .rateLimited: .rateLimited
        case .unavailable: .unavailable
        default: .failed
        }
    }
}

enum LoadFailure { case offline, permissionDenied, rateLimited, unavailable, failed }
enum LoadState<Value> { case idle, loading, loaded(Value), empty, stale(Value, Date), failed(APIError) }
