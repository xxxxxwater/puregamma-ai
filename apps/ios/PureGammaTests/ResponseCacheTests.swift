import XCTest
@testable import PureGamma

final class ResponseCacheTests: XCTestCase {
    func testProtectedCacheRoundTripAndClear() async throws {
        let cache = await ResponseCache()
        let key = "unit-\(UUID().uuidString)"

        try await cache.save("real-server-value", key: key)
        let loaded = try await cache.load(String.self, key: key, maximumAge: 60)

        XCTAssertEqual(loaded?.0, "real-server-value")
        XCTAssertNotNil(loaded?.1)
        try await cache.clear()
        do {
            _ = try await cache.load(String.self, key: key, maximumAge: 60)
            XCTFail("Cleared cache should not be readable")
        } catch {
            XCTAssertTrue(true)
        }
    }
}
