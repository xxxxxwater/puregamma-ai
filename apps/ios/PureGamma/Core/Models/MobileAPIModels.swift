import Foundation

/// 兼容 JSON number 与字符串编码的数值（后端 Numeric 字段可能序列化为字符串）。
struct LenientDecimal: Codable, Equatable {
    let value: Decimal
    init(_ value: Decimal) { self.value = value }
    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if let number = try? container.decode(Decimal.self) { value = number; return }
        if let string = try? container.decode(String.self), let parsed = Decimal(string: string) { value = parsed; return }
        throw DecodingError.typeMismatch(Decimal.self, .init(codingPath: decoder.codingPath, debugDescription: "Expected number or numeric string"))
    }
    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        try container.encode(value)
    }
}

// MARK: - Capabilities

struct MobileCapabilitiesDTO: Decodable {
    // 全部可选：后端逐项开放字段，客户端必须容忍缺失，缺失即视为 false。
    let harnessResearchEnabled, memoryServiceEnabled, autoTradingEnabled, paperTradingEnabled, shadowTradingEnabled, liveTradingEnabled: Bool?
    let userCanStartResearch, userCanManageMemory, userCanViewTradingMandates, userCanPauseMandates: Bool?
    let harnessRetryEnabled: Bool?
    let appMinVersion, maintenanceMessage: String?
    enum CodingKeys: String, CodingKey {
        case appMinVersion = "app_min_version"
        case maintenanceMessage = "maintenance_message"
        case harnessResearchEnabled = "harness_research_enabled"
        case memoryServiceEnabled = "memory_service_enabled"
        case autoTradingEnabled = "auto_trading_enabled"
        case paperTradingEnabled = "paper_trading_enabled"
        case shadowTradingEnabled = "shadow_trading_enabled"
        case liveTradingEnabled = "live_trading_enabled"
        case userCanStartResearch = "user_can_start_research"
        case userCanManageMemory = "user_can_manage_memory"
        case userCanViewTradingMandates = "user_can_view_trading_mandates"
        case userCanPauseMandates = "user_can_pause_mandates"
        case harnessRetryEnabled = "harness_retry_enabled"
    }
    var domain: MobileCapabilities {
        var value = MobileCapabilities()
        value.harnessResearchEnabled = harnessResearchEnabled ?? false
        value.memoryServiceEnabled = memoryServiceEnabled ?? false
        value.autoTradingEnabled = autoTradingEnabled ?? false
        value.paperTradingEnabled = paperTradingEnabled ?? false
        value.shadowTradingEnabled = shadowTradingEnabled ?? false
        value.liveTradingEnabled = liveTradingEnabled ?? false
        value.userCanStartResearch = userCanStartResearch ?? false
        value.userCanManageMemory = userCanManageMemory ?? false
        value.userCanViewTradingMandates = userCanViewTradingMandates ?? false
        value.userCanPauseMandates = userCanPauseMandates ?? false
        value.harnessRetryEnabled = harnessRetryEnabled ?? false
        value.appMinVersion = appMinVersion
        value.maintenanceMessage = maintenanceMessage
        value.serverContractAvailable = true
        return value
    }
}

// MARK: - Research runs

struct ResearchRunCreateDTO: Encodable {
    let name, prompt: String
    let dataSources: [String]
    let skill: String
    enum CodingKeys: String, CodingKey { case name, prompt, skill; case dataSources = "data_sources" }
}

struct ResearchRunsEnvelopeDTO: Codable {
    let runs: [ResearchRunDTO]
    let total: Int?
    let limit: Int?
    let offset: Int?
}

struct ResearchRunEnvelopeDTO: Decodable { let run: ResearchRunDTO }

struct ResearchRunDTO: Codable {
    let id, name: String
    let status: String?
    let verification: String?
    let createdAt, updatedAt: String?
    let creditsUsed, creditsEstimate: LenientDecimal?
    let dataSources: [String]?
    let evidenceCount, citationCount: Int?
    let isDegraded: Bool?
    let errorMessage, summary, disclaimer: String?
    let transitions: [ResearchRunTransitionDTO]?
    enum CodingKeys: String, CodingKey {
        case id, name, status, verification, summary, disclaimer, transitions
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case creditsUsed = "credits_used"
        case creditsEstimate = "credits_estimate"
        case dataSources = "data_sources"
        case evidenceCount = "evidence_count"
        case citationCount = "citation_count"
        case isDegraded = "is_degraded"
        case errorMessage = "error_message"
    }
    var domain: ResearchRun {
        .init(id: id, name: name, state: .init(serverValue: status), verification: .init(serverValue: verification),
              createdAt: createdAt.flatMap(parseUTCDate), updatedAt: updatedAt.flatMap(parseUTCDate),
              creditsUsed: creditsUsed?.value, creditsEstimate: creditsEstimate?.value,
              dataSources: dataSources ?? [],
              evidenceCount: evidenceCount ?? 0, citationCount: citationCount ?? 0,
              isDegraded: isDegraded ?? false, errorMessage: errorMessage, summary: summary, disclaimer: disclaimer,
              transitions: (transitions ?? []).map(\.domain))
    }
}

struct ResearchRunTransitionDTO: Codable {
    let status: String?
    let at: String?
    enum CodingKeys: String, CodingKey { case status; case at = "created_at" }
    var domain: ResearchRunTransition { .init(state: .init(serverValue: status), at: at.flatMap(parseUTCDate)) }
}

struct ResearchEvidenceEnvelopeDTO: Decodable {
    let evidence: [ResearchEvidenceDTO]
    let total: Int?
}

struct ResearchEvidenceDTO: Decodable {
    let id, runID, provider, title: String
    let url: URL?
    let sourceScope, excerpt: String?
    let isVerified: Bool?
    let verificationNote: String?
    let fetchedAt: String?
    let citationIndex: Int?
    enum CodingKeys: String, CodingKey {
        case id, provider, title, url, excerpt
        case runID = "run_id"
        case sourceScope = "source_scope"
        case isVerified = "is_verified"
        case verificationNote = "verification_note"
        case fetchedAt = "fetched_at"
        case citationIndex = "citation_index"
    }
    var domain: ResearchEvidence {
        .init(id: id, runID: runID, provider: provider, title: title, url: url,
              sourceScope: sourceScope, excerpt: excerpt,
              isVerified: isVerified ?? false, verificationNote: verificationNote,
              fetchedAt: fetchedAt.flatMap(parseUTCDate), citationIndex: citationIndex ?? 0)
    }
}

struct ResearchArtifactsEnvelopeDTO: Decodable { let artifacts: [ResearchArtifactDTO] }

struct ResearchArtifactDTO: Decodable {
    let id, type, title: String
    let url: URL?
    let createdAt: String?
    enum CodingKeys: String, CodingKey { case id, type, title, url; case createdAt = "created_at" }
    var domain: ResearchArtifact { .init(id: id, type: type, title: title, url: url, createdAt: createdAt.flatMap(parseUTCDate)) }
}

// MARK: - Memory

struct MemorySettingsEnvelopeDTO: Decodable { let settings: MemorySettingsDTO }

struct MemorySettingsDTO: Codable {
    let shortTermEnabled, midTermEnabled, conversationSummaryEnabled, researchMemoryEnabled, portfolioMemoryEnabled: Bool
    let consentRequired: Bool?
    let retentionDays: Int?
    enum CodingKeys: String, CodingKey {
        case consentRequired = "consent_required"
        case retentionDays = "retention_days"
        case shortTermEnabled = "short_term_enabled"
        case midTermEnabled = "mid_term_enabled"
        case conversationSummaryEnabled = "conversation_summary_enabled"
        case researchMemoryEnabled = "research_memory_enabled"
        case portfolioMemoryEnabled = "portfolio_memory_enabled"
    }
    var domain: MemorySettings {
        .init(shortTermEnabled: shortTermEnabled, midTermEnabled: midTermEnabled,
              conversationSummaryEnabled: conversationSummaryEnabled,
              researchMemoryEnabled: researchMemoryEnabled,
              portfolioMemoryEnabled: portfolioMemoryEnabled,
              consentRequired: consentRequired ?? true, retentionDays: retentionDays ?? 30)
    }
}

struct MemorySettingsPatchDTO: Encodable {
    let shortTermEnabled: Bool?
    let midTermEnabled: Bool?
    let conversationSummaryEnabled: Bool?
    let researchMemoryEnabled: Bool?
    let portfolioMemoryEnabled: Bool?
    let consentGranted: Bool
    enum CodingKeys: String, CodingKey {
        case shortTermEnabled = "short_term_enabled"
        case midTermEnabled = "mid_term_enabled"
        case conversationSummaryEnabled = "conversation_summary_enabled"
        case researchMemoryEnabled = "research_memory_enabled"
        case portfolioMemoryEnabled = "portfolio_memory_enabled"
        case consentGranted = "consent_granted"
    }
}

struct MemoryItemsEnvelopeDTO: Decodable {
    let items: [MemoryItemDTO]
    let total: Int?
}

struct MemoryItemDTO: Decodable {
    let id, scope, kind: String
    let contentPreview: String
    let status: String?
    let createdAt, expiresAt: String?
    enum CodingKeys: String, CodingKey {
        case id, scope, kind, status
        case contentPreview = "content_preview"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
    }
    var domain: MemoryItem {
        .init(id: id, scope: MemoryScope(rawValue: scope) ?? .shortTerm, kind: kind,
              contentPreview: contentPreview,
              lifecycle: .init(serverValue: status),
              createdAt: createdAt.flatMap(parseUTCDate), expiresAt: expiresAt.flatMap(parseUTCDate))
    }
}

struct MemoryProposalsEnvelopeDTO: Decodable { let proposals: [MemoryProposalDTO] }

struct MemoryProposalDTO: Decodable {
    let id, scope, kind: String
    let contentPreview, source, status: String
    let createdAt, expiresAt: String?
    enum CodingKeys: String, CodingKey {
        case id, scope, kind, source, status
        case contentPreview = "content_preview"
        case createdAt = "created_at"
        case expiresAt = "expires_at"
    }
    var domain: MemoryProposal {
        .init(id: id, scope: MemoryScope(rawValue: scope) ?? .shortTerm, kind: kind,
              contentPreview: contentPreview, source: source, status: status,
              createdAt: createdAt.flatMap(parseUTCDate), expiresAt: expiresAt.flatMap(parseUTCDate))
    }
}

struct MemoryProposalEnvelopeDTO: Decodable { let proposal: MemoryProposalDTO }

struct MemoryClearDTO: Encodable { let scope: String }
struct MemoryClearResponseDTO: Decodable { let cleared: Int }
struct MemoryExportDTO: Decodable {
    let url: URL
    let expiresAt: String?
    enum CodingKeys: String, CodingKey { case url; case expiresAt = "expires_at" }
}
struct MemoryItemDeleteResponseDTO: Decodable { let deleted: Bool }

// MARK: - Trading mandates

struct TradingMandatesEnvelopeDTO: Decodable { let mandates: [TradingMandateDTO] }
struct TradingMandateEnvelopeDTO: Decodable { let mandate: TradingMandateDTO }

struct TradingMandateDTO: Decodable {
    let id, name: String
    let strategyName: String?
    let environment: String?
    let paused: Bool?
    let createdAt, updatedAt, lastRunAt: String?
    let lastRunStatus, riskBlockReason: String?
    enum CodingKeys: String, CodingKey {
        case id, name, environment, paused
        case strategyName = "strategy_name"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
        case lastRunAt = "last_run_at"
        case lastRunStatus = "last_run_status"
        case riskBlockReason = "risk_block_reason"
    }
    var domain: TradingMandate {
        .init(id: id, name: name, strategyName: strategyName ?? "—",
              environment: TradingEnvironment(rawValue: environment ?? "") ?? .unavailable,
              paused: paused ?? true,
              createdAt: createdAt.flatMap(parseUTCDate), updatedAt: updatedAt.flatMap(parseUTCDate),
              lastRunAt: lastRunAt.flatMap(parseUTCDate), lastRunStatus: lastRunStatus, riskBlockReason: riskBlockReason)
    }
}

struct MandateStatusDTO: Decodable {
    let environment: String?
    let running, paused, blockedByRisk: Bool?
    let blockReason: String?
    let lastTransitionAt, lastRunAt: String?
    enum CodingKeys: String, CodingKey {
        case environment, running, paused
        case blockedByRisk = "blocked_by_risk"
        case blockReason = "block_reason"
        case lastTransitionAt = "last_transition_at"
        case lastRunAt = "last_run_at"
    }
    var domain: MandateStatus {
        .init(environment: TradingEnvironment(rawValue: environment ?? "") ?? .unavailable,
              running: running ?? false, paused: paused ?? true,
              blockedByRisk: blockedByRisk ?? false, blockReason: blockReason,
              lastTransitionAt: lastTransitionAt, lastRunAt: lastRunAt)
    }
}

struct MandateStatusEnvelopeDTO: Decodable { let status: MandateStatusDTO }

struct MandateRiskDTO: Decodable {
    let maxNotional, dailyLossLimit, maxLeverage: LenientDecimal?
    let maxPositionSizePct: LenientDecimal?
    enum CodingKeys: String, CodingKey {
        case maxNotional = "max_notional"
        case dailyLossLimit = "daily_loss_limit"
        case maxLeverage = "max_leverage"
        case maxPositionSizePct = "max_position_size_pct"
    }
    var domain: MandateRiskLimits { .init(maxNotional: maxNotional?.value, dailyLossLimit: dailyLossLimit?.value, maxLeverage: maxLeverage?.value, maxPositionSizePct: maxPositionSizePct?.value) }
}

struct MandateRiskEnvelopeDTO: Decodable { let risk: MandateRiskDTO }

struct MandatePreviewDTO: Decodable {
    let pendingOrders: Int?
    let riskUtilizationPct: LenientDecimal?
    let asOf: String?
    enum CodingKeys: String, CodingKey {
        case pendingOrders = "pending_orders"
        case riskUtilizationPct = "risk_utilization_pct"
        case asOf = "as_of"
    }
}
struct MandatePreviewEnvelopeDTO: Decodable { let preview: MandatePreviewDTO }
