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

    func request<Response: Decodable, Body: Encodable>(_ path: String, method: String = "GET", body: Body? = Optional<EmptyBody>.none, query: [URLQueryItem] = [], resetsSessionOnUnauthorized: Bool = true) async throws -> Response {
        let data = try await requestData(path, method: method, body: body, query: query, resetsSessionOnUnauthorized: resetsSessionOnUnauthorized)
        do { return try JSONDecoder.pg.decode(Response.self, from: data) }
        catch { throw APIError.decoding(error.localizedDescription) }
    }

    /// The validated response body, for payloads whose shape varies per item
    /// (e.g. the Agent run event log).
    func requestData<Body: Encodable>(_ path: String, method: String = "GET", body: Body? = Optional<EmptyBody>.none, query: [URLQueryItem] = [], resetsSessionOnUnauthorized: Bool = true) async throws -> Data {
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
                try validate(response, data: data, resetsSessionOnUnauthorized: resetsSessionOnUnauthorized)
                return data
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

    /// POST that answers with an SSE stream. `codedErrors` keeps every coded
    /// refusal as `.rejected` so the caller can branch on `code` and read the
    /// envelope's extra fields (the Agent send path needs `runId` from a 409).
    func stream<Body: Encodable>(_ path: String, body: Body, codedErrors: Bool = false) async throws -> (URLSession.AsyncBytes, URLResponse) {
        try await openStream(path: path, method: "POST", body: JSONEncoder.pg.encode(body), codedErrors: codedErrors)
    }

    /// GET-based SSE streams (e.g. research run events). Used by contract v1:
    /// `GET /api/research/runs/{run_id}/events`.
    func streamGet(_ path: String) async throws -> (URLSession.AsyncBytes, URLResponse) {
        try await openStream(path: path, method: "GET", body: nil)
    }

    private func openStream(path: String, method: String, body: Data?, codedErrors: Bool = false) async throws -> (URLSession.AsyncBytes, URLResponse) {
        let url = configuration.baseURL.appending(path: path)
        var request = URLRequest(url: url); request.httpMethod = method; request.timeoutInterval = 120
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
        request.setValue(Self.localeHeader, forHTTPHeaderField: "X-PG-Locale")
        if let token = tokenStore.read() { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body {
            request.httpBody = body
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        do {
            let result = try await session.bytes(for: request)
            if let http = result.1 as? HTTPURLResponse, !(200..<300).contains(http.statusCode) {
                // The error body is the contract (codes, runId); read it
                // instead of validating against an empty body.
                let data = await Self.collect(result.0, limit: 64 * 1024)
                if codedErrors, http.statusCode != 401, APIErrorDetail(status: http.statusCode, body: data).code != nil {
                    let detail = APIErrorDetail(status: http.statusCode, body: data)
                    logFailure(path: path, statusCode: http.statusCode, detail: detail.code ?? "")
                    throw APIError.rejected(detail)
                }
                try validate(result.1, data: data)
            }
            return result
        } catch is CancellationError { throw APIError.canceled }
        catch let error as APIError { throw error }
        catch { throw APIError.transport(error.localizedDescription) }
    }

    private static func collect(_ bytes: URLSession.AsyncBytes, limit: Int) async -> Data {
        var data = Data()
        do {
            for try await byte in bytes {
                data.append(byte)
                if data.count >= limit { break }
            }
        } catch {}
        return data
    }

    private func validate(_ response: URLResponse, data: Data, resetsSessionOnUnauthorized: Bool = true) throws {
        guard let http = response as? HTTPURLResponse else { throw APIError.transport("Non-HTTP response") }
        guard !(200..<300).contains(http.statusCode) else { return }
        let payload = (try? JSONDecoder().decode(ErrorEnvelope.self, from: data))
        let message = payload?.message ?? HTTPURLResponse.localizedString(forStatusCode: http.statusCode)
        switch http.statusCode {
        case 401:
            guard resetsSessionOnUnauthorized else { throw APIError.server(status: 401, message: message) }
            onUnauthorized?(); throw APIError.unauthorized
        case 402: throw APIError.paymentRequired(message)
        case 403: throw APIError.forbidden(message)
        // Not found and conflict carry the decisions (deleted conversation,
        // no trading account, duplicate submission, busy conversation).
        case 404, 409: throw APIError.rejected(APIErrorDetail(status: http.statusCode, body: data))
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
        if case .rejected(let detail) = self { return detail.status }
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

struct EmptyBody: Encodable {}

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
    /// FastAPI error bodies may be a string, a dict, or a validation-error
    /// array. A synthesized memberwise decode only accepts dicts; decode
    /// the detail value through the tolerant Detail instead so array
    /// payloads are not lost.
    enum CodingKeys: String, CodingKey { case detail }
    init(from decoder: Decoder) throws {
        // Normal errors carry {"detail": ...}; FastAPI validation errors are a
        // bare array at the top level, so fall back to the single-value path.
        if let container = try? decoder.container(keyedBy: CodingKeys.self),
           let detail = try? container.decodeIfPresent(Detail.self, forKey: .detail) {
            self.detail = detail
            return
        }
        let container = try decoder.singleValueContainer()
        detail = try? container.decode(Detail.self)
    }
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
        // A naive instant (no offset) is UTC; see parseUTCDate.
        if raw.range(of: #"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$"#, options: .regularExpression) != nil,
           let date = fractional.date(from: raw + "Z") ?? standard.date(from: raw + "Z") { return date }
        throw DecodingError.dataCorruptedError(in: try decoder.singleValueContainer(), debugDescription: "Invalid UTC date")
    } }
}
