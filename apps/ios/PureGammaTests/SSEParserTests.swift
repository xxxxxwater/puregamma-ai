import Foundation
import Testing
@testable import PureGamma

@MainActor struct SSEParserTests {
    @Test func parsesChunkedSSEBlock() throws {
        var parser = SSEParser()
        #expect(parser.consume("event: message.delta") == nil)
        #expect(parser.consume("data: {\"delta\":\"BTC\"}") == nil)
        let parsed = parser.consume("")
        #expect(parsed != nil)
        guard let event = parsed else { return }
        #expect(event.event == "message.delta")
        #expect(String(data: event.data, encoding: .utf8) == "{\"delta\":\"BTC\"}")
    }

    @Test func parsesAllDocumentedEvents() throws {
        let samples = [
            ("run.started", "{\"runId\":\"r1\"}"), ("message.delta", "{\"delta\":\"x\"}"),
            ("tool.started", "{\"tool\":\"quotes\"}"), ("tool.completed", "{\"tool\":\"quotes\"}"),
            ("citation", "{\"index\":1,\"provider\":\"rss\",\"title\":\"Source\",\"url\":\"https://example.com\",\"fetchedAt\":\"2026-07-15T00:00:00+00:00\"}"),
            ("message.completed", "{}"), ("run.failed", "{\"message\":\"failed\"}"), ("run.canceled", "{}")
        ]
        for sample in samples { let event = ServerSentEvent(event: sample.0, data: Data(sample.1.utf8)); _ = try AgentSSEEvent.decode(event) }
    }

    @Test func joinsMultiLineDataWithNewline() {
        var parser = SSEParser()
        _ = parser.consume("event: citation")
        _ = parser.consume("data: {\"index\":1")
        _ = parser.consume("data: ,\"provider\":\"rss\"}")
        let parsed = parser.consume("")
        guard let event = parsed else { Issue.record("Expected event"); return }
        #expect(String(data: event.data, encoding: .utf8) == "{\"index\":1\n,\"provider\":\"rss\"}")
    }

    @Test func ignoresCommentLines() {
        var parser = SSEParser()
        #expect(parser.consume(": keepalive") == nil)
        _ = parser.consume("data: x")
        let parsed = parser.consume("")
        #expect(String(data: parsed!.data, encoding: .utf8) == "x")
    }

    @Test func defaultsEventNameToMessage() {
        var parser = SSEParser()
        _ = parser.consume("data: x")
        let parsed = parser.consume("")
        #expect(parsed?.event == "message")
    }

    @Test func toleratesCRLFLineEndings() {
        var parser = SSEParser()
        _ = parser.consume("event: message.delta\r")
        _ = parser.consume("data: {\"delta\":\"BTC\"}\r")
        let parsed = parser.consume("\r")
        guard let event = parsed else { Issue.record("Expected event"); return }
        #expect(event.event == "message.delta")
        #expect(String(data: event.data, encoding: .utf8) == "{\"delta\":\"BTC\"}")
    }

    @Test func resetsStateBetweenEvents() {
        var parser = SSEParser()
        _ = parser.consume("event: run.started")
        _ = parser.consume("data: {\"runId\":\"r1\"}")
        let first = parser.consume("")
        _ = parser.consume("data: bare")
        let second = parser.consume("")
        #expect(first?.event == "run.started")
        #expect(second?.event == "message")
        #expect(String(data: second!.data, encoding: .utf8) == "bare")
    }
}
