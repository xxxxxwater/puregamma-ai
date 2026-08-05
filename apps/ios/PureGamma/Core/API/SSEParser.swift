import Foundation

struct ServerSentEvent: Equatable, Sendable { let event: String; let data: Data }

struct SSEParser: Sendable {
    private var eventName = "message"
    private var dataLines: [String] = []

    mutating func consume(_ line: String) -> ServerSentEvent? {
        // Defensive: tolerate CRLF line endings if the transport ever delivers
        // them raw (URLSession lines are usually already stripped).
        let line = line.hasSuffix("\r") ? String(line.dropLast()) : line
        if line.isEmpty {
            defer { eventName = "message"; dataLines.removeAll(keepingCapacity: true) }
            guard !dataLines.isEmpty else { return nil }
            return ServerSentEvent(event: eventName, data: Data(dataLines.joined(separator: "\n").utf8))
        }
        if line.hasPrefix(":" ) { return nil }
        let pieces = line.split(separator: ":", maxSplits: 1, omittingEmptySubsequences: false)
        let field = String(pieces[0]); let value = pieces.count > 1 ? String(pieces[1]).trimmingCharacters(in: .whitespaces) : ""
        if field == "event" { eventName = value }
        if field == "data" { dataLines.append(value) }
        return nil
    }
}
