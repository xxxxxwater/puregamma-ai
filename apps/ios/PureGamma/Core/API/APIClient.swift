import Foundation

@MainActor
final class APIClient: @unchecked Sendable {
    let configuration: APIConfiguration
    private let tokenStore: TokenStoring
    private let session: URLSession
    var onUnauthorized: (@MainActor () -> Void)?

    init(configuration: APIConfiguration, tokenStore: TokenStoring, session: URLSession = .shared) {
        self.configuration = configuration; self.tokenStore = tokenStore; self.session = session
    }

    func request<Response: Decodable, Body: Encodable>(_ path: String, method: String = "GET", body: Body? = Optional<EmptyBody>.none, query: [URLQueryItem] = []) async throws -> Response {
        var components = URLComponents(url: configuration.baseURL.appending(path: path), resolvingAgainstBaseURL: false)
        components?.queryItems = query.isEmpty ? nil : query
        guard let url = components?.url else { throw APIError.invalidRequest }
        var request = URLRequest(url: url); request.httpMethod = method; request.timeoutInterval = 20
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        request.setValue(Locale.current.language.languageCode?.identifier ?? "en", forHTTPHeaderField: "X-PG-Locale")
        if let token = tokenStore.read() { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body { request.httpBody = try JSONEncoder.pg.encode(body); request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        do {
            let (data, response) = try await session.data(for: request)
            try validate(response, data: data)
            do { return try JSONDecoder.pg.decode(Response.self, from: data) }
            catch { throw APIError.decoding(error.localizedDescription) }
        } catch is CancellationError { throw APIError.canceled }
        catch let error as APIError { throw error }
        catch { throw APIError.transport(error.localizedDescription) }
    }

    func request<Response: Decodable>(_ path: String, method: String = "GET", query: [URLQueryItem] = []) async throws -> Response {
        try await request(path, method: method, body: Optional<EmptyBody>.none, query: query)
    }

    func stream<Body: Encodable>(_ path: String, body: Body) async throws -> (URLSession.AsyncBytes, URLResponse) {
        let url = configuration.baseURL.appending(path: path)
        var request = URLRequest(url: url); request.httpMethod = "POST"; request.timeoutInterval = 120
        request.setValue("text/event-stream", forHTTPHeaderField: "Accept"); request.setValue("application/json", forHTTPHeaderField: "Content-Type")
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
}

private struct EmptyBody: Encodable {}
private struct ErrorEnvelope: Decodable {
    let detail: Detail?
    var message: String? { detail?.message }
    enum Detail: Decodable {
        case string(String), object(String)
        init(from decoder: Decoder) throws {
            let container = try decoder.singleValueContainer()
            if let text = try? container.decode(String.self) { self = .string(text); return }
            let object = try container.decode([String: String].self)
            self = .object(object["message"] ?? object["code"] ?? String(localized: "Request failed"))
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
