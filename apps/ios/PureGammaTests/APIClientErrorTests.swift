import Foundation
import Testing
@testable import PureGamma

final class MockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.handler else {
            client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL))
            return
        }
        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

private final class MemoryTokenStore: TokenStoring, @unchecked Sendable {
    private var token: String?
    func read() -> String? { token }
    func save(_ token: String) throws { self.token = token }
    func delete() { token = nil }
}

@Suite(.serialized)
@MainActor struct APIClientErrorTests {
    private func makeClient() -> APIClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        return APIClient(
            configuration: APIConfiguration(baseURL: URL(string: "https://api.example.com")!, environment: "test"),
            tokenStore: MemoryTokenStore(),
            session: session
        )
    }

    private func stub(status: Int, body: String = "{}", headers: [String: String] = [:]) {
        MockURLProtocol.handler = { request in
            (HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil, headerFields: headers)!, Data(body.utf8))
        }
    }

    @Test func unauthorizedMapsTo401() async {
        let client = makeClient()
        stub(status: 401, body: #"{"detail":"Invalid token"}"#)
        do {
            let _: EmptyResponseDTO = try await client.request("/me")
            Issue.record("Expected unauthorized")
        } catch let error as APIError {
            #expect(error == .unauthorized)
        } catch {
            Issue.record("Unexpected error: \(error)")
        }
    }

    @Test func unauthorizedInvokesOnUnauthorized() async {
        let client = makeClient()
        stub(status: 401)
        var notified = false
        client.onUnauthorized = { notified = true }
        do {
            let _: EmptyResponseDTO = try await client.request("/me")
            Issue.record("Expected unauthorized")
        } catch {}
        #expect(notified == true)
    }

    @Test func paymentRequiredCarriesServerMessage() async {
        let client = makeClient()
        stub(status: 402, body: #"{"detail":{"code":"INSUFFICIENT_CREDITS","required":8}}"#)
        do {
            let _: EmptyResponseDTO = try await client.request("/x")
            Issue.record("Expected paymentRequired")
        } catch let error as APIError {
            guard case .paymentRequired(let message) = error else { return Issue.record("Wrong error: \(error)") }
            #expect(message == "INSUFFICIENT_CREDITS")
        }
    }

    @Test func forbiddenCarriesObjectMessage() async {
        let client = makeClient()
        stub(status: 403, body: #"{"detail":{"message":"Plan does not include push delivery"}}"#)
        do {
            let _: EmptyResponseDTO = try await client.request("/x")
            Issue.record("Expected forbidden")
        } catch let error as APIError {
            guard case .forbidden(let message) = error else { return Issue.record("Wrong error: \(error)") }
            #expect(message == "Plan does not include push delivery")
        }
    }

    @Test func rateLimitedReadsRetryAfter() async {
        let client = makeClient()
        stub(status: 429, headers: ["Retry-After": "30"])
        do {
            let _: EmptyResponseDTO = try await client.request("/x")
            Issue.record("Expected rateLimited")
        } catch let error as APIError {
            guard case .rateLimited(let seconds) = error else { return Issue.record("Wrong error: \(error)") }
            #expect(seconds == 30)
        }
    }

    @Test func validationErrorsSurfaceFastAPIMessage() async {
        let client = makeClient()
        stub(status: 422, body: #"[{"loc":["body","prompt"],"msg":"field required"}]"#)
        do {
            let _: EmptyResponseDTO = try await client.request("/x")
            Issue.record("Expected server error")
        } catch let error as APIError {
            guard case .server(let status, let message) = error else { return Issue.record("Wrong error: \(error)") }
            #expect(status == 422)
            #expect(message == "field required")
        }
    }

    @Test func retriesTransportFailuresForGETThenSucceeds() async throws {
        let client = makeClient()
        var calls = 0
        MockURLProtocol.handler = { request in
            calls += 1
            if calls < 3 { throw URLError(.notConnectedToInternet) }
            return (HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, Data("{}".utf8))
        }
        let _: EmptyResponseDTO = try await client.request("/market/snapshot")
        #expect(calls == 3)
    }

    @Test func doesNotRetryPOST() async {
        let client = makeClient()
        var calls = 0
        MockURLProtocol.handler = { request in
            calls += 1
            throw URLError(.notConnectedToInternet)
        }
        do {
            let _: EmptyResponseDTO = try await client.request("/billing/checkout", method: "POST", body: ["plan": "pro"])
            Issue.record("Expected transport failure")
        } catch let error as APIError {
            guard case .transport = error else { return Issue.record("Wrong error: \(error)") }
            #expect(calls == 1)
        }
    }
}
