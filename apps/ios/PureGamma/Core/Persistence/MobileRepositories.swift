import Foundation

// MARK: - 后端契约缺失识别（404/501 → "功能暂不可用"，绝不用假数据）

extension APIError {
    /// 新功能接口尚未在后端实现时的错误（404 或 501）。
    var isEndpointMissing: Bool {
        if case .server(let status, _) = self { return status == 404 || status == 501 }
        return false
    }
}

// MARK: - 能力门控存储（Repository 层统一边界）

/// 保存当前服务端 capabilities。AppState 在登录/恢复时写入，注销/401 时重置。
/// 所有移动端 Repository 在执行任何新接口调用前都必须经此校验；
/// UI 门控只作为展示层保护，不是唯一安全边界。
@MainActor final class MobileCapabilitiesStore {
    var capabilities: MobileCapabilities = .unavailable
}

/// Repository 层门控原语。
enum MobileGate {
    @MainActor static func requireContract(_ store: MobileCapabilitiesStore) throws {
        guard store.capabilities.serverContractAvailable else { throw MobileGateError.contractMissing }
    }
    @MainActor static func requireHarnessResearch(_ store: MobileCapabilitiesStore) throws {
        try requireContract(store)
        guard store.capabilities.harnessResearchEnabled else { throw MobileGateError.featureDisabled(String(localized: "Harness research is disabled for your account or plan.")) }
    }
    @MainActor static func requireCanStartResearch(_ store: MobileCapabilitiesStore) throws {
        try requireHarnessResearch(store)
        guard store.capabilities.userCanStartResearch else { throw MobileGateError.featureDisabled(String(localized: "Harness research is disabled for your account or plan.")) }
    }
    @MainActor static func requireMemory(_ store: MobileCapabilitiesStore, mutation: Bool) throws {
        try requireContract(store)
        guard store.capabilities.memoryServiceEnabled else { throw MobileGateError.featureDisabled(String(localized: "Memory service is disabled for your account or plan.")) }
        if mutation, !store.capabilities.userCanManageMemory { throw MobileGateError.featureDisabled(String(localized: "Memory service is disabled for your account or plan.")) }
    }
    @MainActor static func requireMandatesView(_ store: MobileCapabilitiesStore) throws {
        try requireContract(store)
        guard store.capabilities.autoTradingEnabled, store.capabilities.userCanViewTradingMandates else {
            throw MobileGateError.featureDisabled(String(localized: "Auto-trading mandates are disabled for your account. LIVE trading is never available in this app."))
        }
    }
}

// MARK: - 能力发现

@MainActor struct MobileCapabilitiesRepository {
    let client: APIClient
    func capabilities() async throws -> MobileCapabilities {
        let dto: MobileCapabilitiesDTO = try await client.request("/api/mobile/capabilities")
        return dto.domain
    }
}

// MARK: - Harness 研究任务

@MainActor struct ResearchRunsRepository {
    let client: APIClient
    let cache: ResponseCache
    let gate: MobileCapabilitiesStore
    private static let listCacheKey = "research-runs"

    func runs() async throws -> CachedRepositoryValue<[ResearchRun]> {
        try MobileGate.requireHarnessResearch(gate)
        do {
            let dto: ResearchRunsEnvelopeDTO = try await client.request("/api/research/runs")
            try? await cache.save(dto, key: Self.listCacheKey)
            return .init(value: dto.runs.map(\.domain), cachedAt: nil)
        } catch {
            if canUseCache(error), let cached = try? await cache.load(ResearchRunsEnvelopeDTO.self, key: Self.listCacheKey, maximumAge: 300) {
                return .init(value: cached.0.runs.map(\.domain), cachedAt: cached.1)
            }
            throw error
        }
    }

    func run(_ id: String) async throws -> ResearchRun {
        try MobileGate.requireHarnessResearch(gate)
        let runID = try MobileInput.id(id, label: "run identifier")
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs/\(runID)")
        return dto.run.domain
    }

    func create(name: String, prompt: String, dataSources: [String]) async throws -> ResearchRun {
        try MobileGate.requireCanStartResearch(gate)
        let taskName = try MobileInput.text(name, label: "task name", maxLength: MobileInput.nameMaxLength)
        let taskPrompt = try MobileInput.text(prompt, label: "research prompt", maxLength: MobileInput.promptMaxLength)
        let sources = MobileInput.dataSources(dataSources)
        let dto: ResearchRunEnvelopeDTO = try await client.request(
            "/api/research/runs", method: "POST",
            body: ResearchRunCreateDTO(name: taskName, prompt: taskPrompt, dataSources: sources, skill: "harness_deep_research"))
        return dto.run.domain
    }

    func cancel(_ id: String) async throws -> ResearchRun {
        try MobileGate.requireCanStartResearch(gate)
        let runID = try MobileInput.id(id, label: "run identifier")
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs/\(runID)/cancel", method: "POST")
        return dto.run.domain
    }

    func retry(_ id: String) async throws -> ResearchRun {
        try MobileGate.requireCanStartResearch(gate)
        guard gate.capabilities.harnessRetryEnabled else { throw MobileGateError.featureDisabled(String(localized: "Retry is disabled for this run.")) }
        let runID = try MobileInput.id(id, label: "run identifier")
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs/\(runID)/retry", method: "POST")
        return dto.run.domain
    }

    func evidence(_ id: String) async throws -> [ResearchEvidence] {
        try MobileGate.requireHarnessResearch(gate)
        let runID = try MobileInput.id(id, label: "run identifier")
        let dto: ResearchEvidenceEnvelopeDTO = try await client.request("/api/research/runs/\(runID)/evidence")
        return dto.evidence.map(\.domain)
    }

    func artifacts(_ id: String) async throws -> [ResearchArtifact] {
        try MobileGate.requireHarnessResearch(gate)
        let runID = try MobileInput.id(id, label: "run identifier")
        let dto: ResearchArtifactsEnvelopeDTO = try await client.request("/api/research/runs/\(runID)/artifacts")
        return dto.artifacts.map(\.domain)
    }

    /// 订阅任务事件流。断线由调用方决定重连；最终状态必须以 `GET /runs/{id}` 为准。
    func events(_ id: String) async throws -> AsyncThrowingStream<ResearchRunEvent, Error> {
        try MobileGate.requireHarnessResearch(gate)
        let runID = try MobileInput.id(id, label: "run identifier")
        let (bytes, _) = try await client.streamGet("/api/research/runs/\(runID)/events")
        return AsyncThrowingStream { continuation in
            let task = Task {
                do {
                    var parser = SSEParser()
                    for try await line in bytes.lines {
                        if let event = parser.consume(line) { continuation.yield(ResearchRunEvent.decode(event)) }
                    }
                    continuation.finish()
                } catch { continuation.finish(throwing: error) }
            }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
}

// MARK: - Memory

@MainActor struct MemoryRepository {
    let client: APIClient
    let gate: MobileCapabilitiesStore

    func settings() async throws -> MemorySettings {
        try MobileGate.requireMemory(gate, mutation: false)
        let dto: MemorySettingsEnvelopeDTO = try await client.request("/api/memory/settings")
        return dto.settings.domain
    }
    func updateSettings(_ patch: MemorySettingsPatchDTO) async throws -> MemorySettings {
        try MobileGate.requireMemory(gate, mutation: true)
        let dto: MemorySettingsEnvelopeDTO = try await client.request("/api/memory/settings", method: "PATCH", body: patch)
        return dto.settings.domain
    }
    func items(scope: MemoryScope) async throws -> [MemoryItem] {
        try MobileGate.requireMemory(gate, mutation: false)
        let dto: MemoryItemsEnvelopeDTO = try await client.request("/api/memory/items", query: [URLQueryItem(name: "scope", value: scope.rawValue)])
        return dto.items.map(\.domain)
    }
    func proposals() async throws -> [MemoryProposal] {
        try MobileGate.requireMemory(gate, mutation: false)
        let dto: MemoryProposalsEnvelopeDTO = try await client.request("/api/memory/proposals")
        return dto.proposals.map(\.domain)
    }
    func approveProposal(_ id: String) async throws -> MemoryProposal {
        try MobileGate.requireMemory(gate, mutation: true)
        let proposalID = try MobileInput.id(id, label: "proposal identifier")
        let dto: MemoryProposalEnvelopeDTO = try await client.request("/api/memory/proposals/\(proposalID)/approve", method: "POST")
        return dto.proposal.domain
    }
    func rejectProposal(_ id: String) async throws -> MemoryProposal {
        try MobileGate.requireMemory(gate, mutation: true)
        let proposalID = try MobileInput.id(id, label: "proposal identifier")
        let dto: MemoryProposalEnvelopeDTO = try await client.request("/api/memory/proposals/\(proposalID)/reject", method: "POST")
        return dto.proposal.domain
    }
    func deleteItem(_ id: String) async throws {
        try MobileGate.requireMemory(gate, mutation: true)
        let itemID = try MobileInput.id(id, label: "memory item identifier")
        let _: MemoryItemDeleteResponseDTO = try await client.request("/api/memory/items/\(itemID)", method: "DELETE")
    }
    func clear(scope: String) async throws -> Int {
        try MobileGate.requireMemory(gate, mutation: true)
        let safeScope = MobileInput.memoryClearScopes.contains(scope) ? scope : "all"
        let dto: MemoryClearResponseDTO = try await client.request("/api/memory/clear", method: "POST", body: MemoryClearDTO(scope: safeScope))
        return dto.cleared
    }
    func export() async throws -> MemoryExportDTO {
        try MobileGate.requireMemory(gate, mutation: false)
        return try await client.request("/api/memory/export")
    }
}

// MARK: - 自动交易 Mandate（只读 + 有限管理）

@MainActor struct TradingMandatesRepository {
    let client: APIClient
    let gate: MobileCapabilitiesStore

    func mandates() async throws -> [TradingMandate] {
        try MobileGate.requireMandatesView(gate)
        let dto: TradingMandatesEnvelopeDTO = try await client.request("/api/trading/mandates")
        return dto.mandates.map(\.domain)
    }
    func mandate(_ id: String) async throws -> TradingMandate {
        try MobileGate.requireMandatesView(gate)
        let mandateID = try MobileInput.id(id, label: "mandate identifier")
        let dto: TradingMandateEnvelopeDTO = try await client.request("/api/trading/mandates/\(mandateID)")
        return dto.mandate.domain
    }
    func status(_ id: String) async throws -> MandateStatus {
        try MobileGate.requireMandatesView(gate)
        let mandateID = try MobileInput.id(id, label: "mandate identifier")
        let dto: MandateStatusEnvelopeDTO = try await client.request("/api/trading/mandates/\(mandateID)/status")
        return dto.status.domain
    }
    func risk(_ id: String) async throws -> MandateRiskLimits {
        try MobileGate.requireMandatesView(gate)
        let mandateID = try MobileInput.id(id, label: "mandate identifier")
        let dto: MandateRiskEnvelopeDTO = try await client.request("/api/trading/mandates/\(mandateID)/risk")
        return dto.risk.domain
    }

    /// 暂停：Repository 层硬边界 —— 先查环境，仅 PAPER/SHADOW 且能力允许才调用；
    /// 幂等：已暂停时直接返回当前状态，不重复调用服务端。
    func pause(_ id: String) async throws -> TradingMandate {
        try MobileGate.requireMandatesView(gate)
        let mandateID = try MobileInput.id(id, label: "mandate identifier")
        let current = try await mandate(mandateID)
        guard MandateActionPolicy.pauseAllowed(environment: current.environment, paused: current.paused, capabilities: gate.capabilities) else {
            if current.paused { return current }
            if current.environment.isLive { throw MobileGateError.liveDisabled }
            throw MobileGateError.featureDisabled(String(localized: "This mandate cannot be paused from mobile."))
        }
        let dto: TradingMandateEnvelopeDTO = try await client.request("/api/trading/mandates/\(mandateID)/pause", method: "POST")
        return dto.mandate.domain
    }

    /// 恢复：同样的硬边界与幂等语义；服务端仍会二次校验。
    func resume(_ id: String) async throws -> TradingMandate {
        try MobileGate.requireMandatesView(gate)
        let mandateID = try MobileInput.id(id, label: "mandate identifier")
        let current = try await mandate(mandateID)
        guard MandateActionPolicy.resumeAllowed(environment: current.environment, paused: current.paused, capabilities: gate.capabilities) else {
            if !current.paused { return current }
            if current.environment.isLive { throw MobileGateError.liveDisabled }
            throw MobileGateError.featureDisabled(String(localized: "This mandate cannot be resumed from mobile."))
        }
        let dto: TradingMandateEnvelopeDTO = try await client.request("/api/trading/mandates/\(mandateID)/resume", method: "POST")
        return dto.mandate.domain
    }
}
