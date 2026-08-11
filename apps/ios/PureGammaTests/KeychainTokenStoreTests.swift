import Foundation
import Testing
@testable import PureGamma

@MainActor struct KeychainTokenStoreTests {
    private func makeStore() -> KeychainTokenStore {
        KeychainTokenStore(service: "test.ai.puregamma.\(UUID().uuidString)", account: "bearer-token")
    }

    @Test func lifecycleRoundTrip() throws {
        let store = makeStore()
        #expect(store.read() == nil)
        try store.save("token-123")
        #expect(store.read() == "token-123")
        store.delete()
        #expect(store.read() == nil)
    }

    @Test func saveReplacesExistingValue() throws {
        let store = makeStore()
        try store.save("first")
        try store.save("second")
        #expect(store.read() == "second")
        store.delete()
    }

    @Test func deleteIsIdempotent() throws {
        let store = makeStore()
        store.delete()
        store.delete()
        #expect(store.read() == nil)
    }
}
