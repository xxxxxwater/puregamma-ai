import Foundation
import Testing
@testable import PureGamma

@MainActor struct MobileGateTests {
    // MARK: - ID / 输入校验（禁止任意字符串直接拼进 URL）

    @Test func idAcceptsServerStyleIdentifiers() throws {
        let runID = try MobileInput.id("run_01J")
        #expect(runID == "run_01J")
        let mixed = try MobileInput.id("aB-09_")
        #expect(mixed == "aB-09_")
        let trimmed = try MobileInput.id("  m1  ")
        #expect(trimmed == "m1") // 去空白
    }

    @Test func idRejectsTraversalAndInjection() {
        for bad in ["", "../etc/passwd", "..%2F", "a b", "x/y", "http://evil", "javascript:alert(1)", "a?b=c", String(repeating: "x", count: 65)] {
            #expect(throws: MobileGateError.self) {
                _ = try MobileInput.id(bad)
            }
        }
    }

    @Test func dataSourcesAreWhitelistedAndLimited() {
        #expect(MobileInput.dataSources(["market", "news", "research"]) == ["market", "news", "research"])
        #expect(MobileInput.dataSources(["market", "exchange_private", "all", ""]) == ["market"])
        #expect(MobileInput.dataSources(["market", "market", "news", "news"]) == ["market", "news"])
        #expect(MobileInput.dataSources(Array(repeating: "market", count: 20)).count <= 8)
    }

    @Test func textInputsAreLengthLimited() throws {
        #expect(throws: MobileGateError.self) { _ = try MobileInput.text("", label: "name", maxLength: 10) }
        #expect(throws: MobileGateError.self) { _ = try MobileInput.text(String(repeating: "x", count: 11), label: "name", maxLength: 10) }
        let value = try MobileInput.text(" valid ", label: "name", maxLength: 10)
        #expect(value == "valid")
    }

    // MARK: - 门控错误 → APIError 映射（进入既有 LoadState 路径）

    @Test func gateErrorsMapToAPIErrors() {
        // 文案随设备语言变化，断言映射到的错误类别而非具体文本。
        if case .unavailable(let message) = MobileGateError.contractMissing.asAPIError { #expect(!message.isEmpty) } else { Issue.record("contractMissing should map to unavailable") }
        if case .forbidden = MobileGateError.liveDisabled.asAPIError {} else { Issue.record("liveDisabled should map to forbidden") }
        if case .server(let status, _) = MobileGateError.stateConflict("conflict").asAPIError { #expect(status == 409) } else { Issue.record("stateConflict should map to 409") }
        #expect(MobileGateError.featureDisabled("off").asAPIError.presentation == .permissionDenied)
    }

    // MARK: - Repository 层门控（UI 之外的第二道边界）

    private func expectGateBlocked(_ operation: () throws -> Void, sourceLocation: SourceLocation = #_sourceLocation) {
        do {
            try operation()
            Issue.record("Expected MobileGateError to be thrown", sourceLocation: sourceLocation)
        } catch is MobileGateError {
            // 预期：任何门控错误（contractMissing / featureDisabled / liveDisabled …）
        } catch {
            Issue.record("Unexpected error: \(error)", sourceLocation: sourceLocation)
        }
    }

    @Test func gateBlocksWhenContractMissing() {
        let store = MobileCapabilitiesStore()
        expectGateBlocked { try MobileGate.requireHarnessResearch(store) }
        expectGateBlocked { try MobileGate.requireMemory(store, mutation: false) }
        expectGateBlocked { try MobileGate.requireMandatesView(store) }
    }

    @Test func gateBlocksWhenFlagFalse() {
        let store = MobileCapabilitiesStore()
        var capabilities = MobileCapabilities()
        capabilities.serverContractAvailable = true
        store.capabilities = capabilities
        expectGateBlocked { try MobileGate.requireHarnessResearch(store) }
        expectGateBlocked { try MobileGate.requireMemory(store, mutation: true) }
        expectGateBlocked { try MobileGate.requireMandatesView(store) }
    }

    @Test func mutationRequiresManagePermission() {
        let store = MobileCapabilitiesStore()
        var capabilities = MobileCapabilities()
        capabilities.serverContractAvailable = true
        capabilities.memoryServiceEnabled = true
        capabilities.userCanManageMemory = false
        store.capabilities = capabilities
        // 只读不要求 manage 权限，不应被门控。
        do { try MobileGate.requireMemory(store, mutation: false) } catch { Issue.record("Read should not be blocked: \(error)") }
        expectGateBlocked { try MobileGate.requireMemory(store, mutation: true) }
    }

    @Test func unknownEnvironmentDegradesToUnavailable() throws {
        #expect(TradingEnvironment(rawValue: "weird") == nil)
        // DTO 层把未知值降级为 unavailable，绝不当作可操作环境。
        let dto = try JSONDecoder.pg.decode(TradingMandateEnvelopeDTO.self, from: Data(#"{"mandate":{"id":"m1","name":"n","environment":"weird"}}"#.utf8))
        #expect(dto.mandate.domain.environment == .unavailable)
        #expect(!dto.mandate.domain.environment.canBePausedOrResumed)
    }

    @Test func clearScopeWhitelistIsApplied() {
        #expect(MobileInput.memoryClearScopes.contains("all"))
        #expect(MobileInput.memoryClearScopes.contains("short_term"))
        #expect(MobileInput.memoryClearScopes.contains("mid_term"))
        #expect(!MobileInput.memoryClearScopes.contains("DROP TABLE"))
    }
}

// MARK: - 缓存命名空间（用户隔离）

struct CacheNamespaceTests {
    private func makeCache() -> ResponseCache {
        let directory = FileManager.default.temporaryDirectory
            .appending(path: "pg-cache-test-\(UUID().uuidString)", directoryHint: .isDirectory)
        return ResponseCache(directory: directory)
    }

    @Test func namespaceIsolatesUsers() async throws {
        let cache = makeCache()
        let key = "unit-\(UUID().uuidString)"

        await cache.setNamespace("production:user-a")
        try await cache.save("data-of-user-a", key: key)
        let readA = try await cache.load(String.self, key: key, maximumAge: 60)
        #expect(readA?.0 == "data-of-user-a")

        // 切换到 user-b：同一 key 读不到 user-a 的数据（文件不存在 → load 抛错，等价于无缓存）。
        await cache.setNamespace("production:user-b")
        let readB = try? await cache.load(String.self, key: key, maximumAge: 60)
        #expect(readB == nil)

        // 回切 user-a 仍可读；clear 全部清除。
        await cache.setNamespace("production:user-a")
        let readA2 = try await cache.load(String.self, key: key, maximumAge: 60)
        #expect(readA2?.0 == "data-of-user-a")
        try await cache.clear()
        let afterClear = try? await cache.load(String.self, key: key, maximumAge: 60)
        #expect(afterClear == nil)
    }

    @Test func nilNamespaceFallsBackToRawKey() async throws {
        let cache = makeCache()
        let key = "unit-\(UUID().uuidString)"
        try await cache.save("raw", key: key)
        let loaded = try await cache.load(String.self, key: key, maximumAge: 60)
        #expect(loaded?.0 == "raw")
        try await cache.clear()
    }
}
