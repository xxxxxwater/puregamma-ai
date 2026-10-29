import Foundation

// Client half of the Agent session contract (docs/mobile/MOBILE_API_CONTRACT.md §8).
// Everything here is pure or takes its I/O as closures, so the behaviour the
// contract asks for is unit-tested against the shared fixtures without a network.

// MARK: - Idempotent send (§8.1)

enum ClientRequestID {
    /// One id per user-initiated send; a retry of that same send reuses it.
    static func make() -> String { "ios-" + UUID().uuidString.lowercased() }
    static func isValid(_ value: String) -> Bool {
        value.range(of: #"^[A-Za-z0-9_.:-]{8,80}$"#, options: .regularExpression) != nil
    }
}

/// What a failed send means for the turn the user just started.
enum AgentSendFailure: Equatable {
    /// The server already has this exact attempt: follow its run, do not resend.
    case duplicate(runID: String, status: String?)
    /// The conversation was deleted (or is not the caller's).
    case conversationGone
    /// Nothing was started; the same attempt (same request id) may be retried.
    case retryable(APIError)
    /// Nothing was started and resending the same request cannot succeed.
    case final(APIError)

    static func classify(_ error: APIError) -> AgentSendFailure {
        switch error {
        case .rejected(let detail):
            if false, detail.status == 409, detail.code == "DUPLICATE_SUBMISSION", let runID = detail.fields["runId"], !runID.isEmpty {
                return .duplicate(runID: runID, status: detail.fields["status"])
            }
            if detail.status == 404 { return .conversationGone }
            switch detail.code {
            case "AGENT_CONCURRENT_LIMIT_REACHED", "AGENT_GLOBAL_CAPACITY_REACHED", "AGENT_MODEL_UNAVAILABLE": return .retryable(error)
            default: return detail.status >= 500 ? .retryable(error) : .final(error)
            }
        case .transport, .unavailable, .rateLimited: return .retryable(error)
        case .server(let status, _): return status >= 500 ? .retryable(error) : .final(error)
        default: return .final(error)
        }
    }
}

// MARK: - Live frames (§8.7)

enum AgentSSEEvent: Equatable, Sendable {
    case runStarted(String), delta(String), toolStarted(String), toolCompleted(String), citation(AgentSource), completed, failed(String), canceled
    case planReady, evidenceReady, approvalRequired(String)
    /// A frame type this build does not know. The server adds types over time;
    /// an unknown one is skipped, never an error that ends the stream.
    case ignored(String)

    var isTerminal: Bool {
        switch self { case .completed, .failed, .canceled: true; default: false }
    }

    static func decode(_ event: ServerSentEvent) -> AgentSSEEvent {
        AgentStreamFrame.decode(event).event
    }
}

/// One live or replayed frame: its type, its ordering keys and its meaning.
struct AgentStreamFrame: Equatable, Sendable {
    let name: String
    let seq: Int?
    let runID: String?
    let event: AgentSSEEvent

    static func decode(_ event: ServerSentEvent) -> AgentStreamFrame {
        let object = ((try? JSONSerialization.jsonObject(with: event.data)) as? [String: Any]) ?? [:]
        return decode(name: event.event, object: object)
    }

    static func decode(name: String, object: [String: Any]) -> AgentStreamFrame {
        func string(_ keys: String...) -> String { keys.compactMap { object[$0] as? String }.first ?? "" }
        let seq = (object["seq"] as? NSNumber)?.intValue
        let runID = object["runId"] as? String
        let event: AgentSSEEvent
        switch name {
        case "run.started": event = .runStarted(string("runId", "run_id", "id"))
        case "message.delta": event = .delta(string("delta", "content"))
        case "tool.started": event = .toolStarted(string("tool", "name"))
        case "tool.completed": event = .toolCompleted(string("tool", "name"))
        case "citation":
            let index = (object["index"] as? NSNumber)?.intValue ?? 0
            event = .citation(.init(id: "\(index)-\(string("provider"))", provider: string("provider"), title: string("title"), url: URL(string: string("url")),
                                    publishedAt: (object["publishedAt"] as? String).flatMap(parseUTCDate),
                                    sourceTimestamp: (object["sourceTimestamp"] as? String).flatMap(parseUTCDate),
                                    fetchedAt: (object["fetchedAt"] as? String).flatMap(parseUTCDate), citationIndex: index))
        case "message.completed": event = .completed
        case "run.failed": event = .failed(string("message", "error", "code"))
        case "run.canceled": event = .canceled
        case "plan.ready": event = .planReady
        case "evidence.ready": event = .evidenceReady
        case "approval.required": event = .approvalRequired(string("tool"))
        default: event = .failed("Unknown SSE event \(name)")  // MUTATION M1
        }
        return .init(name: name, seq: seq, runID: runID, event: event)
    }
}

/// Which frames of which run this client has already applied.
///
/// Same rules as the web (`isAlreadyApplied` / `isForeignRun`): a frame at or
/// below the cursor is a re-delivery, and a frame naming another run is stale.
struct AgentRunCursor: Equatable, Sendable {
    private(set) var runID: String?
    private(set) var lastSeq = 0

    init(runID: String? = nil, lastSeq: Int = 0) { self.runID = runID; self.lastSeq = lastSeq }

    mutating func attach(to runID: String) {
        if self.runID != runID { self.runID = runID; lastSeq = 0 }
    }

    /// True when the frame is new for the active run; advances the cursor.
    mutating func admit(_ frame: AgentStreamFrame) -> Bool {
        if case .runStarted(let id) = frame.event, runID == nil, !id.isEmpty { runID = id }
        if let foreign = frame.runID, let runID, !runID.isEmpty, foreign != runID { return false }
        if let seq = frame.seq {
            guard seq > lastSeq else { return false }
            lastSeq = seq
        }
        return true
    }

    /// The replay's own high-water mark (it can be ahead of the last stored
    /// frame when ephemeral frames left gaps).
    mutating func advance(to seq: Int) { lastSeq = max(lastSeq, seq) }
}

// MARK: - Event replay (§8.7)

enum AgentRunStatus {
    static let terminal: Set<String> = ["completed", "failed", "canceled", "interrupted"]
    static func isTerminal(_ status: String) -> Bool { terminal.contains(status) }
}

struct AgentRunEventsPage: Equatable, Sendable {
    struct Event: Equatable, Sendable { let seq: Int; let frame: AgentStreamFrame }
    let runID: String
    let status: String
    let messageID: String?
    let conversationID: String?
    let lastSeq: Int
    let truncated: Bool
    let events: [Event]

    /// Parsed by hand: `data` is an arbitrary object per event type.
    static func parse(_ data: Data) throws -> AgentRunEventsPage {
        guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
              let runID = object["runId"] as? String, let status = object["status"] as? String else {
            throw APIError.decoding("Run events page")
        }
        let events = (object["events"] as? [[String: Any]] ?? []).compactMap { row -> Event? in
            guard let seq = (row["seq"] as? NSNumber)?.intValue, let type = row["type"] as? String else { return nil }
            var payload = row["data"] as? [String: Any] ?? [:]
            payload["seq"] = seq
            return Event(seq: seq, frame: AgentStreamFrame.decode(name: type, object: payload))
        }
        return .init(runID: runID, status: status, messageID: object["messageId"] as? String, conversationID: object["conversationId"] as? String,
                     lastSeq: (object["lastSeq"] as? NSNumber)?.intValue ?? 0, truncated: object["truncated"] as? Bool ?? false, events: events)
    }
}

enum AgentRunFollowResult: Equatable {
    /// The server recorded a final status; reload the conversation.
    case finished(String)
    /// The run is not (or no longer) visible to this user.
    case notFound
    /// Observation stopped (view left, app backgrounded, deadline) - not a failure.
    case detached
}

/// Follows a run through its durable event log until the server says it ended.
///
/// A failed poll is not a failed run: network errors wait and retry until the
/// deadline. Only the server's `status` decides the outcome.
@MainActor struct AgentRunFollower {
    var fetch: (_ runID: String, _ after: Int) async throws -> AgentRunEventsPage
    var sleep: (_ seconds: Double) async throws -> Void = { try await Task.sleep(nanoseconds: UInt64($0 * 1_000_000_000)) }
    var pollInterval: Double = 2.5
    var maxPolls = 240

    func follow(runID: String, cursor: inout AgentRunCursor, apply: (AgentStreamFrame) -> Void) async -> AgentRunFollowResult {
        cursor.attach(to: runID)
        var polls = 0
        while polls < maxPolls {
            if Task.isCancelled { return .detached }
            do {
                let page = try await fetch(runID, cursor.lastSeq)
                for event in page.events where cursor.admit(event.frame) { apply(event.frame) }
                cursor.advance(to: page.lastSeq)
                if AgentRunStatus.isTerminal(page.status) { return .finished(page.status) }
                if page.truncated { continue }
            } catch APIError.rejected(let detail) where detail.status == 404 {
                return .notFound
            } catch APIError.canceled {
                return .detached
            } catch is CancellationError {
                return .detached
            } catch {
                // Offline or a proxy hiccup: keep waiting.
            }
            polls += 1
            do { try await sleep(pollInterval) } catch { return .detached }
        }
        return .detached
    }
}

// MARK: - Model menu (§8.5) and permission modes (§8.2)

enum AgentModelMenu {
    struct Entry: Identifiable, Equatable, Sendable {
        let id: String
        let name: String
        let selectable: Bool
        /// Why a model cannot be picked; nil when it can.
        let note: String?
    }

    /// Chat models only: evaluation models never write a reply.
    static func entries(_ models: [AgentModel]) -> [Entry] {
        models.filter { $0.category != "evaluation" }.map { model in
            let selectable = model.available && model.reason == nil
            return Entry(id: model.id, name: model.name, selectable: selectable, note: selectable ? nil : reasonText(model.reason))
        }
    }

    static func reasonText(_ reason: String?) -> String {
        switch reason {
        case "plan_required": String(localized: "Requires a plan upgrade")
        case "pricing_not_configured": String(localized: "Pricing not configured yet")
        default: String(localized: "Unavailable")
        }
    }

    /// The selection to send: the current one while it stays selectable, else `default`.
    static func resolve(_ current: String, in models: [AgentModel]) -> String {
        entries(models).contains(where: { $0.id == current && $0.selectable }) ? current : "default"
    }
}

enum AgentPermissionMode: String, CaseIterable, Identifiable, Sendable {
    case readOnly = "read-only"
    case workspaceWrite = "workspace-write"
    var id: String { rawValue }

    var title: String {
        switch self {
        case .readOnly: String(localized: "Read only")
        case .workspaceWrite: String(localized: "Workspace write")
        }
    }

    /// Only modes the server lists AND this client knows. `full-access` is never offered.
    static func selectable(from server: [String]) -> [AgentPermissionMode] {
        server.compactMap(AgentPermissionMode.init(rawValue:))
    }
}

struct AgentWorkspaceCapabilitiesDTO: Decodable, Sendable {
    let permissionModes: [String]
    let defaultPermissionMode: String?
    enum CodingKeys: String, CodingKey { case permissionModes = "permission_modes"; case defaultPermissionMode = "default_permission_mode" }
}
