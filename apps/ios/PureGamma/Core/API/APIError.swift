import Foundation

enum APIError: LocalizedError, Equatable {
    case invalidRequest, transport(String), unauthorized, paymentRequired(String), forbidden(String), rateLimited(retryAfter: Int?), unavailable(String), server(status: Int, message: String), decoding(String), canceled
    /// A refusal whose machine-readable envelope matters to the caller: every
    /// 404 and 409, and coded errors from the Agent send stream. The `code`
    /// and the extra fields (`runId`, `messageId`, ...) survive intact.
    case rejected(APIErrorDetail)

    var errorDescription: String? {
        switch self {
        case .invalidRequest: String(localized: "Invalid request")
        case .transport: String(localized: "You appear to be offline. Check your connection and retry.")
        case .unauthorized: String(localized: "Your session expired. Please sign in again.")
        case .paymentRequired(let message), .forbidden(let message), .unavailable(let message), .server(_, let message): message
        case .rateLimited(let seconds): seconds.map { String(localized: "Too many requests. Retry in \($0) seconds.") } ?? String(localized: "Too many requests. Please retry later.")
        case .decoding: String(localized: "The server returned an unsupported response.")
        case .canceled: String(localized: "Canceled")
        case .rejected(let detail): detail.displayMessage
        }
    }

    var presentation: LoadFailure {
        switch self {
        case .transport: .offline
        case .forbidden: .permissionDenied
        case .rateLimited: .rateLimited
        case .unavailable: .unavailable
        case .rejected(let detail): detail.presentation
        default: .failed
        }
    }

    /// The server's error code, when the envelope carried one.
    var code: String? { if case .rejected(let detail) = self { detail.code } else { nil } }
    var detail: APIErrorDetail? { if case .rejected(let detail) = self { detail } else { nil } }
}

/// The parts of a FastAPI error body a client may act on.
///
/// `{"detail": {"code": "...", "message": "...", ...}}` keeps every field;
/// `{"detail": "CONVERSATION_BUSY"}` is a bare code; `{"detail": "Conversation
/// not found"}` is only text. See docs/mobile/MOBILE_API_CONTRACT.md §0/§9.
struct APIErrorDetail: Equatable, Sendable {
    let status: Int
    let code: String?
    let message: String?
    /// Every other scalar in the structured detail, as text (`runId`, `status`, ...).
    let fields: [String: String]

    init(status: Int, code: String?, message: String?, fields: [String: String] = [:]) {
        self.status = status; self.code = code; self.message = message; self.fields = fields
    }

    /// Parse a response body; never throws (an unreadable body keeps the status).
    init(status: Int, body: Data) {
        self.status = status
        let object = try? JSONSerialization.jsonObject(with: body)
        let detail = (object as? [String: Any])?["detail"]
        if let structured = detail as? [String: Any] {
            var scalars: [String: String] = [:]
            for (key, value) in structured {
                switch value {
                case let text as String: scalars[key] = text
                case let number as NSNumber: scalars[key] = number.stringValue
                default: continue
                }
            }
            code = scalars.removeValue(forKey: "code")
            message = scalars.removeValue(forKey: "message")
            fields = scalars
        } else if let text = detail as? String {
            // A bare upper-case token is a code; anything else is prose.
            let isCode = text.range(of: #"^[A-Z][A-Z0-9_]{2,}$"#, options: .regularExpression) != nil
            code = isCode ? text : nil
            message = isCode ? nil : text
            fields = [:]
        } else if let list = (detail as? [[String: Any]]) ?? (object as? [[String: Any]]), let first = list.first?["msg"] as? String {
            code = nil; message = first; fields = [:]
        } else {
            code = nil; message = nil; fields = [:]
        }
    }

    var presentation: LoadFailure {
        switch status {
        case 403: .permissionDenied
        case 429: .rateLimited
        case 503: .unavailable
        default: .failed
        }
    }

    /// User-facing text: a known code gets product copy, never a raw code.
    var displayMessage: String {
        switch code {
        case "DUPLICATE_SUBMISSION": String(localized: "This message was already sent. Showing its answer.")
        case "AGENT_DAILY_LIMIT_REACHED": String(localized: "You have used today's Agent runs. Try again tomorrow or upgrade your plan.")
        case "AGENT_CONCURRENT_LIMIT_REACHED": String(localized: "Another answer is still running. Wait for it to finish, then retry.")
        case "AGENT_GLOBAL_CAPACITY_REACHED": String(localized: "The Agent is at capacity. Please retry in a moment.")
        case "INSUFFICIENT_CREDITS": String(localized: "Not enough Credits for this request.")
        case "AGENT_MODEL_INVALID": String(localized: "This model is no longer offered. Pick another model.")
        case "AGENT_MODEL_PLAN_REQUIRED": String(localized: "This model requires an eligible plan.")
        case "AGENT_MODEL_PRICING_NOT_CONFIGURED": String(localized: "This model has no configured price yet, so it cannot be used.")
        case "AGENT_MODEL_UNAVAILABLE": String(localized: "This model is currently unavailable.")
        case "CONVERSATION_BUSY": String(localized: "Wait for the current answer to finish before changing permissions.")
        case "FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED": String(localized: "Full access is no longer offered. Choose read-only or workspace write.")
        case "TRADING_ACCOUNT_NOT_FOUND": String(localized: "No live trading account is connected.")
        default:
            if status == 404 { String(localized: "This item no longer exists.") }
            else { message ?? code ?? HTTPURLResponse.localizedString(forStatusCode: status) }
        }
    }
}

enum LoadFailure { case offline, permissionDenied, rateLimited, unavailable, failed }
enum LoadState<Value> { case idle, loading, loaded(Value), empty, stale(Value, Date), failed(APIError) }
