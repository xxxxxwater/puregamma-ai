import Foundation
import Testing
@testable import PureGamma

struct AgentStreamReducerTests {
    private func message() -> AgentMessage {
        AgentMessage(id: "assistant-1", conversationID: "conversation-1", role: "assistant", content: "", status: "streaming", model: nil, sources: [], createdAt: Date(), errorMessage: nil)
    }

    private func source(_ index: Int) -> AgentSource {
        AgentSource(id: "\(index)-rss", provider: "rss", title: "Source \(index)", url: nil, publishedAt: nil, sourceTimestamp: nil, fetchedAt: nil, citationIndex: index)
    }

    @Test func runStartedCapturesRunID() {
        var reducer = AgentStreamReducer()
        var message = message()
        #expect(reducer.apply(.runStarted("run-42"), to: &message) == .none)
        #expect(reducer.runID == "run-42")
    }

    @Test func deltaAccumulatesContent() {
        var reducer = AgentStreamReducer()
        var message = message()
        _ = reducer.apply(.delta("BTC"), to: &message)
        _ = reducer.apply(.delta(" surged"), to: &message)
        #expect(message.content == "BTC surged")
        #expect(message.status == "streaming")
    }

    @Test func citationIsAppendedOnce() {
        var reducer = AgentStreamReducer()
        var message = message()
        _ = reducer.apply(.citation(source(1)), to: &message)
        _ = reducer.apply(.citation(source(1)), to: &message)
        #expect(message.sources.count == 1)
        #expect(message.sources.first?.citationIndex == 1)
    }

    @Test func toolActivityTracksRunningThenDone() {
        var reducer = AgentStreamReducer()
        var message = message()
        _ = reducer.apply(.toolStarted("quotes"), to: &message)
        #expect(reducer.toolActivity == ["RUNNING · quotes"])
        _ = reducer.apply(.toolStarted("news"), to: &message)
        #expect(reducer.toolActivity.count == 2)
        _ = reducer.apply(.toolCompleted("quotes"), to: &message)
        #expect(reducer.toolActivity == ["RUNNING · news", "DONE · quotes"])
    }

    @Test func toolCompletedIsIdempotentAndExact() {
        var reducer = AgentStreamReducer()
        var message = message()
        _ = reducer.apply(.toolStarted("news"), to: &message)
        _ = reducer.apply(.toolCompleted("news"), to: &message)
        _ = reducer.apply(.toolCompleted("news"), to: &message)
        #expect(reducer.toolActivity == ["DONE · news"])
        // A tool whose name is a substring of another must not clear it.
        _ = reducer.apply(.toolStarted("news_research"), to: &message)
        _ = reducer.apply(.toolCompleted("news"), to: &message)
        #expect(reducer.toolActivity == ["RUNNING · news_research", "DONE · news"])
    }

    @Test func completedTerminatesStream() {
        var reducer = AgentStreamReducer()
        var message = message()
        _ = reducer.apply(.runStarted("run-1"), to: &message)
        #expect(reducer.apply(.completed, to: &message) == .completed)
        #expect(message.status == "completed")
        #expect(reducer.isStreaming == false)
        #expect(reducer.runID == nil)
    }

    @Test func failedSetsErrorAndStopsStreaming() {
        var reducer = AgentStreamReducer()
        var message = message()
        #expect(reducer.apply(.failed("Upstream timeout"), to: &message) == .failed("Upstream timeout"))
        #expect(message.status == "failed")
        #expect(message.errorMessage == "Upstream timeout")
        #expect(reducer.isStreaming == false)
    }

    @Test func canceledStopsStreaming() {
        var reducer = AgentStreamReducer()
        var message = message()
        #expect(reducer.apply(.canceled, to: &message) == .canceled)
        #expect(message.status == "canceled")
        #expect(reducer.isStreaming == false)
        #expect(reducer.runID == nil)
    }
}
