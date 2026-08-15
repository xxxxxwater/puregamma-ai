import Foundation

// MARK: - 能力发现（所有新功能的唯一总开关，以服务端返回为准）

struct MobileCapabilities: Equatable, Sendable {
    var harnessResearchEnabled = false
    var memoryServiceEnabled = false
    var autoTradingEnabled = false
    var paperTradingEnabled = false
    var shadowTradingEnabled = false
    /// 仅作信息展示。无论该值为何，移动端都不提供 LIVE 启动入口。
    var liveTradingEnabled = false
    var userCanStartResearch = false
    var userCanManageMemory = false
    var userCanViewTradingMandates = false
    var userCanPauseMandates = false
    var harnessRetryEnabled = false
    var appMinVersion: String?
    var maintenanceMessage: String?
    /// `false` 表示后端尚未提供 `/api/mobile/capabilities`，全部新功能按不可用处理。
    var serverContractAvailable = false

    static let unavailable = MobileCapabilities()
}

// MARK: - Harness 研究任务

/// 服务端研究任务状态 + 客户端提交态。服务端永远不会返回 `idle`/`submitting`。
enum ResearchRunState: String, Equatable, Sendable, CaseIterable {
    case idle, submitting
    case queued, preparing, running, validating
    case completed, degraded, failed, canceled
    case timedOut = "timed_out"

    init(serverValue: String?) {
        self = Self.allCases.first { $0.rawValue == serverValue } ?? .idle
    }

    var serverRawValue: String? { self == .idle || self == .submitting ? nil : rawValue }

    var isTerminal: Bool {
        switch self {
        case .completed, .degraded, .failed, .canceled, .timedOut: true
        default: false
        }
    }

    var isActive: Bool {
        switch self {
        case .queued, .preparing, .running, .validating: true
        default: false
        }
    }

    /// 失败/超时后允许重试的状态（重试是否可用仍以服务端 `harness_retry_enabled` 为准）。
    var isRetryable: Bool { self == .failed || self == .canceled || self == .timedOut }
}

/// 研究结果的可靠性分级。必须与"尚未完成"分开展示，且一律附免责声明。
enum ResearchVerification: String, Equatable, Sendable {
    case verified, partial, degraded, failed, incomplete

    init(serverValue: String?) { self = Self(rawValue: serverValue ?? "") ?? .incomplete }
}

struct ResearchRun: Identifiable, Equatable, Sendable {
    let id, name: String
    var state: ResearchRunState
    var verification: ResearchVerification
    let createdAt, updatedAt: Date?
    let creditsUsed, creditsEstimate: Decimal?
    let dataSources: [String]
    let evidenceCount, citationCount: Int
    var isDegraded: Bool
    var errorMessage: String?
    let summary: String?
    let disclaimer: String?
    let transitions: [ResearchRunTransition]

    var effectiveVerification: ResearchVerification {
        if !state.isTerminal { return .incomplete }
        if verification == .degraded || isDegraded { return .degraded }
        return verification
    }
}

struct ResearchRunTransition: Identifiable, Equatable, Sendable {
    var id: String { "\(state.rawValue)-\(at?.timeIntervalSince1970 ?? 0)" }
    let state: ResearchRunState
    let at: Date?
}

struct ResearchEvidence: Identifiable, Equatable, Sendable {
    let id, runID, provider, title: String
    let url: URL?
    let sourceScope, excerpt: String?
    let isVerified: Bool
    let verificationNote: String?
    let fetchedAt: Date?
    let citationIndex: Int
}

struct ResearchArtifact: Identifiable, Equatable, Sendable {
    let id, type, title: String
    let url: URL?
    let createdAt: Date?
}

/// 研究任务 SSE 事件。未知事件一律解码为 `.unknown`，绝不抛错。
enum ResearchRunEvent: Equatable, Sendable {
    case stateChanged(ResearchRunState)
    case progress(stage: String, percent: Int)
    case evidenceAdded(count: Int)
    case completed(verified: Bool, degraded: Bool)
    case failed(String)
    case canceled
    case unknown

    static func decode(_ event: ServerSentEvent) -> ResearchRunEvent {
        let object = (try? JSONSerialization.jsonObject(with: event.data) as? [String: Any]) ?? [:]
        func string(_ keys: String...) -> String { keys.compactMap { object[$0] as? String }.first ?? "" }
        switch event.event {
        case "run.queued": return .stateChanged(.queued)
        case "run.state": return .stateChanged(.init(serverValue: string("status", "state")))
        case "run.progress":
            let percent = (object["progress_pct"] as? Int) ?? (object["progress"] as? Int) ?? 0
            return .progress(stage: string("stage"), percent: percent)
        case "run.evidence": return .evidenceAdded(count: (object["evidence_count"] as? Int) ?? 0)
        case "run.completed":
            return .completed(verified: (object["verified"] as? Bool) ?? false, degraded: (object["degraded"] as? Bool) ?? false)
        case "run.failed": return .failed(string("message", "error", "code"))
        case "run.canceled": return .canceled
        default: return .unknown
        }
    }
}

// MARK: - Memory

enum MemoryState: Equatable, Sendable {
    case disabled, enabled, consentRequired, loading, loaded, error(String)

    static func state(settings: MemorySettings, consentGranted: Bool) -> MemoryState {
        if settings.consentRequired && !consentGranted { return .consentRequired }
        let anyEnabled = settings.shortTermEnabled || settings.midTermEnabled || settings.conversationSummaryEnabled || settings.researchMemoryEnabled || settings.portfolioMemoryEnabled
        return anyEnabled ? .enabled : .disabled
    }
}

enum MemoryScope: String, Equatable, Sendable, CaseIterable, Identifiable {
    case shortTerm = "short_term", midTerm = "mid_term"
    var id: String { rawValue }
}

enum MemoryItemLifecycle: String, Equatable, Sendable {
    case saved, pending, rejected, expired, deleted
    init(serverValue: String?) { self = Self(rawValue: serverValue ?? "") ?? .saved }
}

struct MemorySettings: Equatable, Sendable {
    var shortTermEnabled: Bool
    var midTermEnabled: Bool
    var conversationSummaryEnabled: Bool
    var researchMemoryEnabled: Bool
    var portfolioMemoryEnabled: Bool
    let consentRequired: Bool
    let retentionDays: Int

    static let allOff = MemorySettings(shortTermEnabled: false, midTermEnabled: false, conversationSummaryEnabled: false, researchMemoryEnabled: false, portfolioMemoryEnabled: false, consentRequired: true, retentionDays: 30)

    /// 默认不记忆敏感信息。此列表同时用于服务端策略与移动端展示文案。
    static let neverStoredCategories = ["private_keys", "api_secrets", "card_details", "auth_tokens", "account_credentials", "unconfirmed_trade_intent", "unverified_harness_inference", "auto_trade_orders"]
}

struct MemoryItem: Identifiable, Equatable, Sendable {
    let id: String
    let scope: MemoryScope
    let kind: String
    let contentPreview: String
    let lifecycle: MemoryItemLifecycle
    let createdAt, expiresAt: Date?
}

struct MemoryProposal: Identifiable, Equatable, Sendable {
    let id: String
    let scope: MemoryScope
    let kind, contentPreview, source: String
    let status: String
    let createdAt, expiresAt: Date?
    var isPending: Bool { status == "pending" }
}

// MARK: - 自动交易 Mandate（只读 + 有限管理）

enum TradingEnvironment: String, Equatable, Sendable {
    case off, paper, shadow
    case liveDisabled = "live_disabled"
    case unavailable

    /// LIVE 在任何配置下都不可操作。该策略为客户端硬约束，不受任何 Flag 影响。
    var isLive: Bool { self == .liveDisabled }
    var canBePausedOrResumed: Bool { self == .paper || self == .shadow }
}

struct TradingMandate: Identifiable, Equatable, Sendable {
    let id, name, strategyName: String
    let environment: TradingEnvironment
    let paused: Bool
    let createdAt, updatedAt, lastRunAt: Date?
    let lastRunStatus, riskBlockReason: String?
}

struct MandateRiskLimits: Equatable, Sendable {
    let maxNotional, dailyLossLimit, maxLeverage: Decimal?
    let maxPositionSizePct: Decimal?
}

struct MandateStatus: Equatable, Sendable {
    let environment: TradingEnvironment
    let running, paused, blockedByRisk: Bool
    let blockReason, lastTransitionAt, lastRunAt: String?
}

/// 移动端允许的动作策略。所有动作仍需服务端二次校验；本策略只决定 UI 是否渲染按钮。
enum MandateActionPolicy: Sendable {
    static func pauseAllowed(environment: TradingEnvironment, paused: Bool, capabilities: MobileCapabilities) -> Bool {
        environment.canBePausedOrResumed && !paused && capabilities.userCanPauseMandates && capabilities.autoTradingEnabled
    }
    static func resumeAllowed(environment: TradingEnvironment, paused: Bool, capabilities: MobileCapabilities) -> Bool {
        environment.canBePausedOrResumed && paused && capabilities.userCanPauseMandates && capabilities.autoTradingEnabled
    }
    /// LIVE 永远不可操作：即使 capability、部署标记或本地配置全部开启。
    static func liveActionAllowed(environment: TradingEnvironment) -> Bool { false }
}

// MARK: - Repository 层统一门控（UI 门控之外的硬边界）

/// capabilities 缺失/加载失败/字段为 false 时，Repository 层直接抛出的错误。
/// 服务端仍做最终权限校验；这里的门控只防止客户端发出无权请求。
enum MobileGateError: LocalizedError, Equatable {
    case contractMissing
    case featureDisabled(String)
    case invalidInput(String)
    case liveDisabled
    case stateConflict(String)

    var errorDescription: String? {
        switch self {
        case .contractMissing: String(localized: "Feature not available yet")
        case .featureDisabled(let message): message
        case .invalidInput(let message): message
        case .liveDisabled: String(localized: "LIVE is disabled and cannot be started from this app.")
        case .stateConflict(let message): message
        }
    }

    /// 统一转为 APIError，供 LoadState 与既有错误展示路径使用。
    var asAPIError: APIError {
        switch self {
        case .contractMissing: .unavailable(errorDescription ?? "Feature not available yet")
        case .featureDisabled: .forbidden(errorDescription ?? "Disabled")
        case .invalidInput: .server(status: 400, message: errorDescription ?? "Invalid input")
        case .liveDisabled: .forbidden(errorDescription ?? "LIVE disabled")
        case .stateConflict: .server(status: 409, message: errorDescription ?? "State conflict")
        }
    }
}

/// 路径参数与输入校验：禁止把用户输入的任意字符串直接拼进 URL。
/// `scope`、`dataSources`、`run_id`、`mandate_id` 全部走白名单与长度限制。
enum MobileInput {
    private static let idRegex = /^[A-Za-z0-9_-]{1,64}$/
    static let allowedDataSources: Set<String> = ["market", "news", "research"]
    static let memoryClearScopes: Set<String> = ["all", "short_term", "mid_term"]
    static let nameMaxLength = 100
    static let promptMaxLength = 4000
    static let dataSourceMaxCount = 8
    static let dataSourceMaxLength = 32

    static func id(_ raw: String, label: String = "identifier") throws -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= 64, trimmed.wholeMatch(of: idRegex) != nil else {
            throw MobileGateError.invalidInput(String(localized: "Invalid \(label)"))
        }
        return trimmed
    }

    static func text(_ raw: String, label: String, maxLength: Int) throws -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, trimmed.count <= maxLength else {
            throw MobileGateError.invalidInput(String(localized: "Invalid \(label)"))
        }
        return trimmed
    }

    static func dataSources(_ raw: [String]) -> [String] {
        Array(Set(raw)).prefix(dataSourceMaxCount)
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
            .filter { !$0.isEmpty && $0.count <= dataSourceMaxLength && allowedDataSources.contains($0) }
            .sorted()
    }
}

extension Error {
    /// 统一错误映射：MobileGateError 与 APIError 都进入既有 LoadState 展示路径。
    var mobileAPIError: APIError {
        if let gate = self as? MobileGateError { return gate.asAPIError }
        if let api = self as? APIError { return api }
        return .unavailable(localizedDescription)
    }
}
