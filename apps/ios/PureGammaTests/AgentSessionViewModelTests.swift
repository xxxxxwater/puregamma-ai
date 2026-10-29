import Foundation
import Testing
@testable import PureGamma

/// A URLProtocol of its own, so these tests never race the handler that
/// APIClientErrorTests installs on MockURLProtocol.
final class AgentStubProtocol: URLProtocol {
    struct Call { let method: String; let path: String; let body: [String: Any] }
    nonisolated(unsafe) static var handler: ((URLRequest, [String: Any]) throws -> (Int, Data, String))?
    nonisolated(unsafe) static var calls: [Call] = []

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var data = request.httpBody ?? Data()
        if data.isEmpty, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(buffer, count: count) }
        }
        let body = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any] ?? [:]
        Self.calls.append(Call(method: request.httpMethod ?? "GET", path: request.url?.path ?? "", body: body))
        guard let handler = Self.handler else { client?.urlProtocol(self, didFailWithError: URLError(.unsupportedURL)); return }
        do {
            let (status, payload, type) = try handler(request, body)
            let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": type])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: payload)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }
    override func stopLoading() {}
}

private final class StubTokenStore: TokenStoring, @unchecked Sendable {
    func read() -> String? { "token" }
    func save(_ token: String) throws {}
    func delete() {}
}

@Suite(.serialized)
@MainActor struct AgentSessionViewModelTests {
    private let conversationID = "00000000-0000-4000-8000-000000000001"

    private func makeModel() -> AgentViewModel {
        AgentStubProtocol.calls = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [AgentStubProtocol.self]
        let client = APIClient(configuration: APIConfiguration(baseURL: URL(string: "https://api.example.com")!, environment: "test"),
                               tokenStore: StubTokenStore(), session: URLSession(configuration: configuration))
        let model = AgentViewModel(repository: AgentRepository(client: client))
        model.replayPollInterval = 0.01
        model.selectedConversation = AgentConversation(id: conversationID, title: "t", status: "active", summary: nil, createdAt: Date(), updatedAt: Date(), archivedAt: nil)
        model.messages = .empty
        return model
    }

    /// The conversation as the server has it after the turn, with no active run.
    private func settledSnapshot() throws -> Data {
        var body = try ContractFixture.body("agent_conversation_active_run.json")
        body["active_run_id"] = NSNull(); body["active_run_message_id"] = NSNull(); body["pending_approvals"] = []
        return try JSONSerialization.data(withJSONObject: body)
    }

    private func waitUntilIdle(_ model: AgentViewModel) async {
        for _ in 0..<400 where model.isStreaming { try? await Task.sleep(nanoseconds: 10_000_000) }
    }

    private var sends: [AgentStubProtocol.Call] { AgentStubProtocol.calls.filter { $0.method == "POST" && $0.path.hasSuffix("/messages") } }

    @Test func aDuplicateSubmissionAttachesToTheOriginalRunInsteadOfResending() async throws {
        let model = makeModel()
        // The 409 fixture, reporting the original run as still going.
        var envelope = try ContractFixture.body("agent_send_duplicate_409.json")
        var detail = envelope["detail"] as! [String: Any]; detail["status"] = "running"; envelope["detail"] = detail
        let duplicate = try JSONSerialization.data(withJSONObject: envelope)
        let running = try ContractFixture.body("agent_run_events_running.json")
        var completed = running; completed["status"] = "completed"; completed["events"] = []
        let pages = [try JSONSerialization.data(withJSONObject: running), try JSONSerialization.data(withJSONObject: completed)]
        let snapshot = try settledSnapshot()
        var polls = 0
        AgentStubProtocol.handler = { request, _ in
            let path = request.url!.path
            if path.hasSuffix("/messages") { return (409, duplicate, "application/json") }
            if path.contains("/runs/") { polls += 1; return (200, pages[min(polls, 2) - 1], "application/json") }
            return (200, snapshot, "application/json")
        }

        model.prompt = "What moved BTC today?"
        await model.send(locale: "en")
        await waitUntilIdle(model)

        #expect(sends.count == 1)                       // never resent
        #expect(polls >= 2)                              // followed the original run's log
        #expect(AgentStubProtocol.calls.contains { $0.path.hasSuffix("/runs/00000000-0000-4000-8000-000000000001/events") })
        #expect(model.composerError == nil)              // not reported as an error
        #expect(model.pendingAttempt == nil)
        guard case .loaded(let rows) = model.messages else { Issue.record("messages not loaded"); return }
        #expect(!rows.contains { $0.id.hasPrefix("local-") })  // server record replaced the optimistic rows
    }

    @Test func retryingAnUnsentAttemptReusesItsRequestID() async throws {
        let model = makeModel()
        AgentStubProtocol.handler = { _, _ in throw URLError(.notConnectedToInternet) }
        model.prompt = "What moved BTC today?"
        await model.send(locale: "en")
        await waitUntilIdle(model)
        #expect(model.pendingAttempt != nil)
        #expect(model.composerError?.presentation == .offline)

        let stream = try ContractFixture.text("agent_send_stream_completed.sse")
        let snapshot = try settledSnapshot()
        AgentStubProtocol.handler = { request, _ in
            request.url!.path.hasSuffix("/messages") ? (200, Data(stream.utf8), "text/event-stream") : (200, snapshot, "application/json")
        }
        await model.retry(locale: "en")
        await waitUntilIdle(model)

        let ids = sends.compactMap { $0.body["client_request_id"] as? String }
        #expect(ids.count == 2 && ids[0] == ids[1])
        #expect(ClientRequestID.isValid(ids[0]))
        #expect(model.composerError == nil && model.pendingAttempt == nil)

        // A new question gets a new id.
        model.prompt = "And ETH?"
        await model.send(locale: "en")
        await waitUntilIdle(model)
        let all = sends.compactMap { $0.body["client_request_id"] as? String }
        #expect(all.count == 3 && all[2] != all[0])
    }

    @Test func anUnknownFrameDoesNotEndTheTurn() async throws {
        let model = makeModel()
        let stream = try ContractFixture.text("agent_send_stream_completed.sse")
            .replacingOccurrences(of: "event: evidence.ready", with: "event: workspace.preview\ndata: {\"kind\": \"chart\"}\n\nevent: evidence.ready")
        let snapshot = try settledSnapshot()
        AgentStubProtocol.handler = { request, _ in
            request.url!.path.hasSuffix("/messages") ? (200, Data(stream.utf8), "text/event-stream") : (200, snapshot, "application/json")
        }
        model.prompt = "What is the BTC market price?"
        await model.send(locale: "en")
        await waitUntilIdle(model)
        #expect(model.composerError == nil)
        #expect(model.connection == nil)
        // A complete stream needs no replay.
        #expect(!AgentStubProtocol.calls.contains { $0.path.contains("/runs/") })
    }

    @Test func aStreamThatDropsBeforeItsEndIsRestoredFromTheLog() async throws {
        let model = makeModel()
        let full = try ContractFixture.text("agent_send_stream_completed.sse")
        let cut = String(full[..<full.range(of: "event: tool.completed")!.lowerBound])  // body ends mid-run
        let snapshot = try settledSnapshot()
        var completed = try ContractFixture.body("agent_run_events_running.json"); completed["status"] = "completed"
        let page = try JSONSerialization.data(withJSONObject: completed)
        AgentStubProtocol.handler = { request, _ in
            let path = request.url!.path
            if path.hasSuffix("/messages") { return (200, Data(cut.utf8), "text/event-stream") }
            if path.contains("/runs/") { return (200, page, "application/json") }
            return (200, snapshot, "application/json")
        }
        model.prompt = "What is the BTC market price?"
        await model.send(locale: "en")
        await waitUntilIdle(model)
        let replay = AgentStubProtocol.calls.first { $0.path.contains("/runs/") }
        #expect(replay?.path == "/api/agent/runs/00000000-0000-4000-8000-000000000001/events")
        #expect(sends.count == 1)
        #expect(model.composerError == nil)  // an interrupted connection is not a failed run
    }

    @Test func aDeletedConversationIsRemovedAndExplained() async throws {
        let model = makeModel()
        let gone = try ContractFixture.http("agent_conversation_deleted_404.json")
        AgentStubProtocol.handler = { _, _ in (404, gone.body, "application/json") }
        let row = model.selectedConversation!
        let other = AgentConversation(id: "other", title: "o", status: "active", summary: nil, createdAt: Date(), updatedAt: Date(), archivedAt: nil)
        model.conversations = .loaded([row, other])

        await model.open(row)

        guard case .loaded(let rows) = model.conversations else { Issue.record("list cleared"); return }
        #expect(rows.map(\.id) == ["other"])
        #expect(model.selectedConversation == nil)
        #expect(model.notice != nil)
        #expect(model.composerError == nil)
    }

    @Test func reopeningAConversationReattachesToItsActiveRun() async throws {
        let model = makeModel()
        let active = try ContractFixture.http("agent_conversation_active_run.json").body
        let settled = try settledSnapshot()
        var completed = try ContractFixture.body("agent_run_events_running.json"); completed["status"] = "completed"
        let page = try JSONSerialization.data(withJSONObject: completed)
        var opened = 0
        AgentStubProtocol.handler = { request, _ in
            if request.url!.path.contains("/runs/") { return (200, page, "application/json") }
            opened += 1
            return (200, opened == 1 ? active : settled, "application/json")
        }
        await model.open(model.selectedConversation!)
        await waitUntilIdle(model)
        #expect(AgentStubProtocol.calls.contains { $0.path == "/api/agent/runs/00000000-0000-4000-8000-000000000004/events" })
        #expect(!AgentStubProtocol.calls.contains { $0.path.hasSuffix("/cancel") })
    }

    @Test func goingToTheBackgroundStopsObservingWithoutCanceling() async throws {
        let model = makeModel()
        let active = try ContractFixture.http("agent_conversation_active_run.json").body
        let running = try ContractFixture.http("agent_run_events_running.json").body
        AgentStubProtocol.handler = { request, _ in
            (200, request.url!.path.contains("/runs/") ? running : active, "application/json")
        }
        model.replayPollInterval = 0.05
        await model.open(model.selectedConversation!)
        #expect(model.isStreaming)
        model.detach()
        #expect(!model.isStreaming)
        try await Task.sleep(nanoseconds: 100_000_000)
        #expect(!AgentStubProtocol.calls.contains { $0.path.hasSuffix("/cancel") })
    }

    @Test func onlyAnExplicitStopCancelsTheRun() async throws {
        let model = makeModel()
        let active = try ContractFixture.http("agent_conversation_active_run.json").body
        let running = try ContractFixture.http("agent_run_events_running.json").body
        AgentStubProtocol.handler = { request, _ in
            let path = request.url!.path
            if path.hasSuffix("/cancel") { return (200, Data(#"{"id":"r","status":"canceled"}"#.utf8), "application/json") }
            return (200, path.contains("/runs/") ? running : active, "application/json")
        }
        model.replayPollInterval = 0.05
        await model.open(model.selectedConversation!)
        await model.cancel()
        #expect(AgentStubProtocol.calls.contains { $0.method == "POST" && $0.path == "/api/agent/runs/00000000-0000-4000-8000-000000000004/cancel" })
        #expect(!model.isStreaming)
    }
}
