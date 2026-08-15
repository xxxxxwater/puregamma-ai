import Foundation
import Testing
@testable import PureGamma

@MainActor struct ResearchRunEventTests {
    private func event(_ name: String, _ data: String) -> ServerSentEvent {
        ServerSentEvent(event: name, data: Data(data.utf8))
    }

    @Test func decodesDocumentedEvents() {
        #expect(ResearchRunEvent.decode(event("run.queued", "{}")) == .stateChanged(.queued))
        #expect(ResearchRunEvent.decode(event("run.state", #"{"status":"running"}"#)) == .stateChanged(.running))
        #expect(ResearchRunEvent.decode(event("run.state", #"{"status":"timed_out"}"#)) == .stateChanged(.timedOut))
        #expect(ResearchRunEvent.decode(event("run.progress", #"{"stage":"evidence","progress_pct":42}"#)) == .progress(stage: "evidence", percent: 42))
        #expect(ResearchRunEvent.decode(event("run.evidence", #"{"evidence_count":3}"#)) == .evidenceAdded(count: 3))
        #expect(ResearchRunEvent.decode(event("run.completed", #"{"verified":true,"degraded":false}"#)) == .completed(verified: true, degraded: false))
        #expect(ResearchRunEvent.decode(event("run.failed", #"{"message":"boom"}"#)) == .failed("boom"))
        #expect(ResearchRunEvent.decode(event("run.canceled", "{}")) == .canceled)
    }

    @Test func unknownEventsBecomeUnknownInsteadOfThrowing() {
        // 契约要求：新增事件类型不得导致解析崩溃。
        #expect(ResearchRunEvent.decode(event("run.new_feature", #"{"x":1}"#)) == .unknown)
        #expect(ResearchRunEvent.decode(event("totally.unknown", "not json")) == .unknown)
    }

    @Test func malformedDataDoesNotThrow() {
        #expect(ResearchRunEvent.decode(event("run.state", "not valid json")) == .stateChanged(.idle))
        #expect(ResearchRunEvent.decode(event("run.progress", "{}")) == .progress(stage: "", percent: 0))
    }

    @Test func stateTerminalAndRetryableSemantics() {
        #expect(ResearchRunState.completed.isTerminal)
        #expect(ResearchRunState.degraded.isTerminal)
        #expect(ResearchRunState.failed.isTerminal)
        #expect(ResearchRunState.canceled.isTerminal)
        #expect(ResearchRunState.timedOut.isTerminal)
        #expect(!ResearchRunState.running.isTerminal)
        #expect(ResearchRunState.failed.isRetryable)
        #expect(ResearchRunState.timedOut.isRetryable)
        #expect(!ResearchRunState.completed.isRetryable)
        #expect(!ResearchRunState.running.isRetryable)
    }

    @Test func activeStatesExcludeTerminal() {
        #expect(ResearchRunState.queued.isActive)
        #expect(ResearchRunState.validating.isActive)
        #expect(!ResearchRunState.completed.isActive)
        #expect(!ResearchRunState.canceled.isActive)
    }

    @Test func sseParserStillTolerantOfUnknownEventNames() {
        var parser = SSEParser()
        _ = parser.consume("event: research.new_event")
        _ = parser.consume("data: {\"a\":1}")
        let parsed = parser.consume("")
        #expect(parsed?.event == "research.new_event")
    }
}
