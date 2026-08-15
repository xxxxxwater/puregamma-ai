import Foundation

// MARK: - 后端契约缺失识别（404/501 → "功能暂不可用"，绝不用假数据）

extension APIError {
    /// 新功能接口尚未在后端实现时的错误（404 或 501）。
    var isEndpointMissing: Bool {
        if case .server(let status, _) = self { return status == 404 || status == 501 }
        return false
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
    private static let listCacheKey = "research-runs"

    func runs() async throws -> CachedRepositoryValue<[ResearchRun]> {
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
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs/\(id)")
        return dto.run.domain
    }

    func create(name: String, prompt: String, dataSources: [String]) async throws -> ResearchRun {
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs", method: "POST", body: ResearchRunCreateDTO(name: name, prompt: prompt, dataSources: dataSources, skill: "harness_deep_research"))
        return dto.run.domain
    }

    func cancel(_ id: String) async throws -> ResearchRun {
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs/\(id)/cancel", method: "POST")
        return dto.run.domain
    }

    func retry(_ id: String) async throws -> ResearchRun {
        let dto: ResearchRunEnvelopeDTO = try await client.request("/api/research/runs/\(id)/retry", method: "POST")
        return dto.run.domain
    }

    func evidence(_ id: String) async throws -> [ResearchEvidence] {
        let dto: ResearchEvidenceEnvelopeDTO = try await client.request("/api/research/runs/\(id)/evidence")
        return dto.evidence.map(\.domain)
    }

    func artifacts(_ id: String) async throws -> [ResearchArtifact] {
        let dto: ResearchArtifactsEnvelopeDTO = try await client.request("/api/research/runs/\(id)/artifacts")
        return dto.artifacts.map(\.domain)
    }

    /// 订阅任务事件流。断线由调用方决定重连；最终状态必须以 `GET /runs/{id}` 为准。
    func events(_ id: String) async throws -> AsyncThrowingStream<ResearchRunEvent, Error> {
        let (bytes, _) = try await client.streamGet("/api/research/runs/\(id)/events")
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
    func settings() async throws -> MemorySettings {
        let dto: MemorySettingsEnvelopeDTO = try await client.request("/api/memory/settings")
        return dto.settings.domain
    }
    func updateSettings(_ patch: MemorySettingsPatchDTO) async throws -> MemorySettings {
        let dto: MemorySettingsEnvelopeDTO = try await client.request("/api/memory/settings", method: "PATCH", body: patch)
        return dto.settings.domain
    }
    func items(scope: MemoryScope) async throws -> [MemoryItem] {
        let dto: MemoryItemsEnvelopeDTO = try await client.request("/api/memory/items", query: [URLQueryItem(name: "scope", value: scope.rawValue)])
        return dto.items.map(\.domain)
    }
    func proposals() async throws -> [MemoryProposal] {
        let dto: MemoryProposalsEnvelopeDTO = try await client.request("/api/memory/proposals")
        return dto.proposals.map(\.domain)
    }
    func approveProposal(_ id: String) async throws -> MemoryProposal {
        let dto: MemoryProposalEnvelopeDTO = try await client.request("/api/memory/proposals/\(id)/approve", method: "POST")
        return dto.proposal.domain
    }
    func rejectProposal(_ id: String) async throws -> MemoryProposal {
        let dto: MemoryProposalEnvelopeDTO = try await client.request("/api/memory/proposals/\(id)/reject", method: "POST")
        return dto.proposal.domain
    }
    func deleteItem(_ id: String) async throws {
        let _: MemoryItemDeleteResponseDTO = try await client.request("/api/memory/items/\(id)", method: "DELETE")
    }
    func clear(scope: String) async throws -> Int {
        let dto: MemoryClearResponseDTO = try await client.request("/api/memory/clear", method: "POST", body: MemoryClearDTO(scope: scope))
        return dto.cleared
    }
    func export() async throws -> MemoryExportDTO {
        try await client.request("/api/memory/export")
    }
}

// MARK: - 自动交易 Mandate（只读 + 有限管理）

@MainActor struct TradingMandatesRepository {
    let client: APIClient
    func mandates() async throws -> [TradingMandate] {
        let dto: TradingMandatesEnvelopeDTO = try await client.request("/api/trading/mandates")
        return dto.mandates.map(\.domain)
    }
    func mandate(_ id: String) async throws -> TradingMandate {
        let dto: TradingMandateEnvelopeDTO = try await client.request("/api/trading/mandates/\(id)")
        return dto.mandate.domain
    }
    func status(_ id: String) async throws -> MandateStatus {
        let dto: MandateStatusEnvelopeDTO = try await client.request("/api/trading/mandates/\(id)/status")
        return dto.status.domain
    }
    func risk(_ id: String) async throws -> MandateRiskLimits {
        let dto: MandateRiskEnvelopeDTO = try await client.request("/api/trading/mandates/\(id)/risk")
        return dto.risk.domain
    }
    /// 暂停/恢复由服务端再次校验；移动端 UI 已用 `MandateActionPolicy` 门控，LIVE 永不渲染按钮。
    func pause(_ id: String) async throws -> TradingMandate {
        let dto: TradingMandateEnvelopeDTO = try await client.request("/api/trading/mandates/\(id)/pause", method: "POST")
        return dto.mandate.domain
    }
    func resume(_ id: String) async throws -> TradingMandate {
        let dto: TradingMandateEnvelopeDTO = try await client.request("/api/trading/mandates/\(id)/resume", method: "POST")
        return dto.mandate.domain
    }
}
