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
}
