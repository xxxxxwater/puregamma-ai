import Foundation
import os

@MainActor
final class APIClient: @unchecked Sendable {
    let configuration: APIConfiguration
    private let tokenStore: TokenStoring
    private let session: URLSession
    private let logger = Logger(subsystem: "ai.puregamma.ios", category: "api")
    var onUnauthorized: (@MainActor () -> Void)?

    /// Transient-failure retries for idempotent requests only (GET/PUT/DELETE).
    private static let maxRetries = 2
    private static let retryableMethods: Set<String> = ["GET", "PUT", "DELETE"]
    private static let retryBaseDelay: TimeInterval = 0.5

    init(configuration: APIConfiguration, tokenStore: TokenStoring, session: URLSession = .shared) {
        self.configuration = configuration; self.tokenStore = tokenStore; self.session = session
    }

    func request<Response: Decodable, Body: Encodable>(_ path: String, method: String = "GET", body: Body? = Optional<EmptyBody>.none, query: [URLQueryItem] = []) async throws -> Response {
        var components = URLComponents(url: configuration.baseURL.appending(path: path), resolvingAgainstBaseURL: false)
        components?.queryItems = query.isEmpty ? nil : query
        guard let url = components?.url else { throw APIError.invalidRequest }
        var request = URLRequest(url: url); request.httpMethod = method; request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(Self.localeHeader, forHTTPHeaderField: "X-PG-Locale")
        if let token = tokenStore.read() { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONEncoder.pg.encode(body); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let maxAttempts = Self.retryableMethods.contains(method) ? Self.maxRetries : 0
        var attempt = 0
        while true {
            do {
                let (data, response) = try await session.data(for: request)
                try validate(response, data: data)
                do { return try JSONDecoder.pg.decode(Response.self, from: data) }
                catch { throw APIError.decoding(error.localizedDescription) }
            } catch is CancellationError { throw APIError.canceled }
            catch let error as APIError {
                if attempt < maxAttempts, Self.shouldRetry(error) {
                    attempt += 1
                    try? await Task.sleep(for: .seconds(Self.retryBaseDelay * Double(attempt)))
                    continue
                }
                logFailure(path: path, statusCode: error.statusCode, detail: error.localizedDescription)
                throw error
            }
            catch {
                if attempt < maxAttempts {
                    attempt += 1
                    try? await Task.sleep(for: .seconds(Self.retryBaseDelay * Double(attempt)))
                    continue
                }
                logFailure(path: path, statusCode: nil, detail: error.localizedDescription)
                throw APIError.transport(error.localizedDescription)
            }
        }
    }

    func request<Response: Decodable>(_ path: String, method: String = "GET", query: [URLQueryItem] = []) async throws -> Response {
        try await request(path, method: method, body: Optional<EmptyBody>.none, query: query)
    }

    func stream<Body: Encodable>(_ path: String, body: Body) async throws -> (URLSession.AsyncBytes, URLResponse) {
        let url = configuration.baseURL.appending(path: path)
        var request = URLRequest(url: url); request.httpMethod = "POST"; request.timeoutInterval = 120
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept"); request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.setValue(Self.localeHeader, forHTTPHeaderField: "X-PG-Locale")
        if let token = tokenStore.read() { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        request.httpBody = try JSONEncoder.pg.encode(body)
        do {
            let result = try await session.bytes(for: request)
            try validate(result.1, data: Data())
            return result
        } catch is CancellationError { throw APIError.canceled }
        catch let error as APIError { throw error }
        catch { throw APIError.transport(error.localizedDescription) }
    }

    private func validate(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.transport("Non-HTTP response") }
        guard !(200..<300).contains(http.statusCode) else { return }
        let payload = (try? JSONDecoder().decode(ErrorEnvelope.self, from: data))
        let message = payload?.message ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
        switch http.statusCode {
        case 401: onUnauthorized?(); throw APIError.unauthorized
        case 402: throw APIError.paymentRequired(message)
        case 403: throw APIError.forbidden(message)
        case 429: throw APIError.rateLimited(retryAfter: Int(http.value(forHTTPHeaderField: "Retry-After") ?? ""))
        case 503: throw APIError.unavailable(message)
        default: throw APIError.server(status: http.statusCode, message: message)
        }
    }

    private static func shouldRetry(_ error: APIError) -> Bool {
        switch error {
        case .transport: true
        case .unavailable: true
        case .server(let status, _): status >= 500
        default: false
        }
    }

    /// The effective in-app language so server responses match the user's choice,
    /// not just the device locale (the app overrides `\.locale` at the root).
    private static var localeHeader: String {
        switch UserDefaults.standard.string(forKey: "app.language") {
        case "chinese": "zh-Hans"
        case "english": "en"
        default: Locale.current.language.languageCode?.identifier ?? "en"
        }
    }

    private func logFailure(path: String, statusCode: Int?, detail: String) {
        logger.error("API \(path) failed (status: \(statusCode.map(String.init) ?? "transport"), detail: \(detail, privacy: .public))")
    }
}

extension APIError {
    var statusCode: Int? {
        if case .server(let status, _) = self { return status }
        switch self {
        case .unauthorized: return 401
        case .paymentRequired: return 402
        case .forbidden: return 403
        case .rateLimited: return 429
        case .unavailable: return 503
        default: return nil
        }
    }
}

private struct EmptyBody: Encodable {}

/// Lenient scalar used so error envelopes with non-string metadata still decode.
/// `{"code": "INSUFFICIENT_CREDITS", "required": 8}` or FastAPI's validation
/// array `[{"loc": [...], "msg": "..."}]` must not silently lose the message.
private enum LooseValue: Decodable {
    case text(String), number(Double), flag(Bool), other
    var text: String? { if case .text(let value) = self { value } else { nil } }
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let value = try? container.decode(String.self) { self = .text(value); return }
        if let value = try? container.decode(Double.self) { self = .number(value); return }
        if let value = try? container.decode(Bool.self) { self = .flag(value); return }
        self = .other
    }
}

private struct ErrorEnvelope: Decodable {
    let detail: Detail?
    var message: String? { detail?.message }
    enum Detail: Decodable {
        case string(String), object(String)
        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let text = try? container.decode(String.self) { self = .string(text); return }
            if let object = try? container.decode([String: LooseValue].self) {
                if let message = object["message"]?.text ?? object["code"]?.text { self = .object(message); return }
            }
            if let list = try? container.decode([[String: LooseValue]].self), let message = list.first?["msg"]?.text {
                self = .object(message); return
            }
            self = .object(String(localized: "Request failed"))
        }
        var message: String { switch self { case .string(let value), .object(let value): value } }
    }
}

extension JSONDecoder {
    static var pg: JSONDecoder { let value = JSONDecoder(); value.dateDecodingStrategy = .iso8601Flexible; return value }
}
extension JSONEncoder { static var pg: JSONEncoder { let value = JSONEncoder(); value.dateEncodingStrategy = .iso8601; return value } }
extension JSONDecoder.DateDecodingStrategy {
    static var iso8601Flexible: JSONDecoder.DateDecodingStrategy { .custom { decoder in
        let raw = try decoder.singleValueContainer().decode(String.self)
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        let standard = ISO8601DateFormatter()
        standard.formatOptions = [.withInternetDateTime]
        if let date = fractional.date(from: raw) ?? standard.date(from: raw) { return date }
        throw DecodingError.dataCorruptedError(in: try decoder.singleValueContainer(), debugDescription: "Invalid UTC date")
    } }
}
