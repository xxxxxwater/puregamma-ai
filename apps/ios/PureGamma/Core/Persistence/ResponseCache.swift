import CryptoKit
import Foundation

struct CachedRepositoryValue<Value> {
    let value: Value
    let cachedAt: Date?
    var isStale: Bool { cachedAt != nil }
}

actor ResponseCache {
    private struct Entry<Value: Codable>: Codable {
        let savedAt: Date
        let value: Value
    }

    private let directory: URL

    init() {
        let base = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        directory = base.appending(path: "PureGamma/ResponseCache", directoryHint: .isDirectory)
    }

    func save<Value: Codable>(_ value: Value, key: String) throws {
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        let encoder = JSONEncoder()
        encoder.dateEncodingStrategy = .iso8601
        let data = try encoder.encode(Entry(savedAt: Date(), value: value))
        try data.write(to: url(for: key), options: [.atomic, .completeFileProtection])
    }

    func load<Value: Codable>(_ type: Value.Type, key: String, maximumAge: TimeInterval) throws -> (Value, Date)? {
        let data = try Data(contentsOf: url(for: key))
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .iso8601
        let entry = try decoder.decode(Entry<Value>.self, from: data)
        guard Date().timeIntervalSince(entry.savedAt) <= maximumAge else {
            try? FileManager.default.removeItem(at: url(for: key))
            return nil
        }
        return (entry.value, entry.savedAt)
    }

    func clear() throws {
        guard FileManager.default.fileExists(atPath: directory.path) else { return }
        try FileManager.default.removeItem(at: directory)
    }

    private func url(for key: String) -> URL {
        let digest = SHA256.hash(data: Data(key.utf8)).map { String(format: "%02x", $0) }.joined()
        return directory.appending(path: "\(digest).json")
    }
}
