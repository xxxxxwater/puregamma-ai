import Foundation
import Testing
@testable import PureGamma

/// The server's own responses, shared with the Android tests and pinned by
/// tests/contract/test_mobile_agent_contract.py (docs/mobile/fixtures).
enum ContractFixture {
    static let directory: URL = URL(fileURLWithPath: #filePath)
        .deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent().deletingLastPathComponent()
        .appending(path: "docs/mobile/fixtures")

    static func text(_ name: String) throws -> String { try String(contentsOf: directory.appending(path: name), encoding: .utf8) }

    /// `(status, body)` of an HTTP fixture; the body re-serialised as JSON bytes.
    static func http(_ name: String) throws -> (status: Int, body: Data) {
        let object = try JSONSerialization.jsonObject(with: Data(try text(name).utf8)) as! [String: Any]
        return (object["status"] as! Int, try JSONSerialization.data(withJSONObject: object["body"]!))
    }

    static func body(_ name: String) throws -> [String: Any] {
        try JSONSerialization.jsonObject(with: try http(name).body) as! [String: Any]
    }

    static func frames(_ sse: String) -> [ServerSentEvent] {
        var parser = SSEParser(); var frames: [ServerSentEvent] = []
        for line in sse.components(separatedBy: "\n") { if let frame = parser.consume(line) { frames.append(frame) } }
        return frames
    }
}

@MainActor struct MobileContractFixtureTests {
    // MARK: (a) idempotent send

    @Test func requestIDsMatchTheServerPattern() {
        let first = ClientRequestID.make(), second = ClientRequestID.make()
        #expect(ClientRequestID.isValid(first) && ClientRequestID.isValid(second))
        #expect(first != second)
        #expect(!ClientRequestID.isValid("short") && !ClientRequestID.isValid("has spaces in it"))
    }

    @Test func duplicateSubmissionKeepsTheOriginalRun() throws {
        let fixture = try ContractFixture.http("agent_send_duplicate_409.json")
        let detail = APIErrorDetail(status: fixture.status, body: fixture.body)
        #expect(detail.code == "DUPLICATE_SUBMISSION")
        #expect(detail.fields["runId"] == "00000000-0000-4000-8000-000000000001")
        #expect(detail.fields["messageId"] != nil && detail.fields["userMessageId"] != nil)
        #expect(AgentSendFailure.classify(.rejected(detail)) == .duplicate(runID: "00000000-0000-4000-8000-000000000001", status: detail.fields["status"]))
    }

    @Test func sendRefusalsAreClassifiedByCode() throws {
        let cases: [(String, String)] = [
            ("agent_send_limit_429.json", "retryable"), ("agent_send_insufficient_credits_402.json", "final"),
            ("agent_send_model_invalid_400.json", "final"), ("agent_send_model_plan_required_403.json", "final"),
            ("agent_send_model_unavailable_503.json", "retryable"), ("agent_send_model_pricing_503.json", "final"),
        ]
        for (name, expected) in cases {
            let fixture = try ContractFixture.http(name)
            let detail = APIErrorDetail(status: fixture.status, body: fixture.body)
            #expect(detail.code != nil, "\(name) lost its code")
            // Product copy, never a raw code.
            #expect(detail.displayMessage != detail.code)
            switch AgentSendFailure.classify(.rejected(detail)) {
            case .retryable: #expect(expected == "retryable", "\(name)")
            case .final: #expect(expected == "final", "\(name)")
            default: Issue.record("\(name) misclassified")
            }
        }
    }

    // MARK: (b) permission modes

    @Test func onlyReadOnlyAndWorkspaceWriteAreOffered() throws {
        let body = try ContractFixture.http("agent_workspace_capabilities.json").body
        let dto = try JSONDecoder.pg.decode(AgentWorkspaceCapabilitiesDTO.self, from: body)
        #expect(AgentPermissionMode.selectable(from: dto.permissionModes) == [.readOnly, .workspaceWrite])
        #expect(AgentPermissionMode.selectable(from: ["read-only", "full-access"]) == [.readOnly])
        for name in ["agent_permission_full_access_400.json", "agent_permission_busy_409.json"] {
            let fixture = try ContractFixture.http(name)
            let detail = APIErrorDetail(status: fixture.status, body: fixture.body)
            #expect(detail.code == (fixture.status == 400 ? "FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED" : "CONVERSATION_BUSY"))
        }
    }

    // MARK: (c)(e) NAV

    @Test func navWithoutAnAccountIsAnEmptyStateNotZero() throws {
        for name in ["portfolio_nav_no_account_404.json", "portfolio_nav_history_no_account_404.json", "portfolio_positions_no_account_404.json"] {
            let fixture = try ContractFixture.http(name)
            #expect(LiveNavState.isNoAccount(.rejected(APIErrorDetail(status: fixture.status, body: fixture.body))), "\(name)")
        }
        #expect(!LiveNavState.isNoAccount(.rejected(APIErrorDetail(status: 404, code: nil, message: "Conversation not found"))))
    }

    @Test func navAmountsAreExactDecimals() throws {
        let envelope = try JSONDecoder.pg.decode(LiveNavEnvelopeDTO.self, from: ContractFixture.http("portfolio_nav_200.json").body)
        let nav = envelope.domain
        #expect(nav.nav == Decimal(string: "101234.56789012"))
        #expect(nav.netExposure == Decimal(string: "-1.00000001"))
        #expect(nav.realizedPnl == 0)
        #expect(nav.dailyPnl == Decimal(string: "1234.56789012"))
        #expect(nav.calculatedAt != nil)  // naive timestamps are read as UTC
        let history = try JSONDecoder.pg.decode(LiveNavHistoryDTO.self, from: ContractFixture.http("portfolio_nav_history_200.json").body)
        #expect(history.history.map(\.domain.nav) == [Decimal(string: "101234.56789012"), Decimal(string: "100000.00000000")])
        // An unpriced NAV stays nil.
        let unpriced = #"{"id":"n","account_id":"a","currency":"USD","nav":null,"cash":"1.5","gross_exposure":"0","net_exposure":"0","realized_pnl":"0","unrealized_pnl":"0","is_stale":true}"#
        #expect(try JSONDecoder.pg.decode(LiveNavDTO.self, from: Data(unpriced.utf8)).domain.nav == nil)
    }

    // MARK: (d) deleted conversation

    @Test func deletedConversationIsRecognised() throws {
        let fixture = try ContractFixture.http("agent_conversation_deleted_404.json")
        let detail = APIErrorDetail(status: fixture.status, body: fixture.body)
        #expect(detail.code == nil && detail.message == "Conversation not found")
        #expect(AgentSendFailure.classify(.rejected(detail)) == .conversationGone)
    }

    // MARK: (f) model menu

    @Test func modelMenuHidesEvaluationAndExplainsUnavailableModels() throws {
        let body = try ContractFixture.body("agent_capabilities_models.json")
        let data = try JSONSerialization.data(withJSONObject: body["models"]!)
        let models = try JSONDecoder.pg.decode([ModelDTO].self, from: data).map(\.domain)
        let menu = AgentModelMenu.entries(models)
        #expect(!menu.contains { $0.id == "jev" })
        #expect(menu.first { $0.id == "default" }?.selectable == true)
        #expect(menu.first { $0.id == "gpt-6-sol" }?.note == AgentModelMenu.reasonText("pricing_not_configured"))
        #expect(menu.first { $0.id == "gpt-5.6-luna" }?.note == AgentModelMenu.reasonText("plan_required"))
        #expect(menu.filter(\.selectable).map(\.id) == ["default"])
        #expect(AgentModelMenu.resolve("gpt-6-sol", in: models) == "default")
        #expect(AgentModelMenu.resolve("jev", in: models) == "default")
    }

    // MARK: (g) frames, cursor, replay

    @Test func everyFrameOfARealStreamDecodesInOrder() throws {
        let frames = ContractFixture.frames(try ContractFixture.text("agent_send_stream_completed.sse")).map(AgentStreamFrame.decode)
        #expect(frames.first?.event == .runStarted("00000000-0000-4000-8000-000000000001"))
        #expect(frames.last?.event == .completed)
        #expect(frames.compactMap(\.seq) == Array(1...frames.count))
        #expect(!frames.contains { if case .ignored = $0.event { true } else { false } })
    }

    @Test func unknownFramesAreIgnoredAndTheStreamContinues() throws {
        var sse = try ContractFixture.text("agent_send_stream_completed.sse")
        sse = sse.replacingOccurrences(of: "event: plan.ready", with: "event: dream.started\ndata: {\"note\": \"a frame type this build does not know\"}\n\nevent: plan.ready")
        var reducer = AgentStreamReducer(); var cursor = AgentRunCursor()
        var message = AgentMessage(id: "a", conversationID: "c", role: "assistant", content: "", status: "streaming", model: nil, sources: [], createdAt: Date(), errorMessage: nil)
        var effects: [AgentStreamReducer.Effect] = []
        for frame in ContractFixture.frames(sse).map(AgentStreamFrame.decode) where cursor.admit(frame) {
            effects.append(reducer.apply(frame.event, to: &message))
        }
        #expect(AgentSSEEvent.decode(ServerSentEvent(event: "dream.started", data: Data("{}".utf8))) == .ignored("dream.started"))
        #expect(effects.last == .completed)
        #expect(message.status == "completed" && message.content == "Mock LLM synthesis for institutional research.")
    }

    @Test func cursorDropsReplayedAndForeignFrames() {
        var cursor = AgentRunCursor()
        let started = AgentStreamFrame(name: "run.started", seq: 1, runID: "r1", event: .runStarted("r1"))
        #expect(cursor.admit(started) && cursor.runID == "r1")
        #expect(!cursor.admit(started))  // re-delivered
        #expect(cursor.admit(.init(name: "message.delta", seq: 2, runID: nil, event: .delta("x"))))
        #expect(!cursor.admit(.init(name: "tool.started", seq: 3, runID: "other", event: .toolStarted("t"))))  // another run
        #expect(cursor.admit(.init(name: "message.completed", seq: 4, runID: "r1", event: .completed)))
        #expect(cursor.lastSeq == 4)
    }

    @Test func replayPagesParseForEveryStatus() throws {
        for status in ["running", "canceled", "interrupted"] {
            let page = try AgentRunEventsPage.parse(ContractFixture.http("agent_run_events_\(status).json").body)
            #expect(page.status == status)
            #expect(page.events.map(\.seq) == (status == "canceled" ? [2, 3, 5, 6] : [2, 3, 5]))
            #expect(page.lastSeq == page.events.last?.seq)
            #expect(AgentRunStatus.isTerminal(status) == (status != "running"))
            #expect((page.events.last?.frame.event == .canceled) == (status == "canceled"))
        }
    }

    @Test func followerWaitsThroughNetworkErrorsUntilTheServerSaysDone() async throws {
        let running = try AgentRunEventsPage.parse(ContractFixture.http("agent_run_events_running.json").body)
        var calls: [Int] = []
        let follower = AgentRunFollower(fetch: { _, after in
            calls.append(after)
            switch calls.count {
            case 1: throw APIError.transport("offline")
            case 2: return running
            default: return AgentRunEventsPage(runID: running.runID, status: "completed", messageID: nil, conversationID: nil, lastSeq: 5, truncated: false, events: running.events)
            }
        }, sleep: { _ in })
        var cursor = AgentRunCursor(runID: running.runID, lastSeq: 1)
        var applied: [Int] = []
        let result = await follower.follow(runID: running.runID, cursor: &cursor) { applied.append($0.seq ?? -1) }
        #expect(result == .finished("completed"))
        #expect(calls == [1, 1, 5])
        #expect(applied == [2, 3, 5])  // the re-sent page applied nothing twice
    }

    @Test func followerStopsOnAnotherUsersRun() async throws {
        let fixture = try ContractFixture.http("agent_run_events_not_found_404.json")
        let follower = AgentRunFollower(fetch: { _, _ in throw APIError.rejected(APIErrorDetail(status: fixture.status, body: fixture.body)) }, sleep: { _ in })
        var cursor = AgentRunCursor()
        let result = await follower.follow(runID: "r", cursor: &cursor) { _ in }
        #expect(result == .notFound)
    }

    @Test func conversationSnapshotNamesTheActiveRun() throws {
        let dto = try JSONDecoder.pg.decode(ConversationDetailDTO.self, from: ContractFixture.http("agent_conversation_active_run.json").body)
        #expect(dto.snapshot.activeRunID == "00000000-0000-4000-8000-000000000004")
        #expect(dto.snapshot.conversation.permissionMode == "workspace-write")
    }

    @Test func endedRunsAreCaptioned() {
        #expect(AgentMessageView.endedCaption("canceled") != nil)
        #expect(AgentMessageView.endedCaption("interrupted") != nil)
        #expect(AgentMessageView.endedCaption("completed") == nil)
    }
}
