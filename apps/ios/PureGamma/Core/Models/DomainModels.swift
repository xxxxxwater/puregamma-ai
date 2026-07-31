import Foundation

struct User: Identifiable, Equatable, Sendable { let id, email, name, role, plan: String; let creditBalance: Int; let avatarURL: URL?; let locale: String }
struct MarketAsset: Identifiable, Equatable, Sendable {
    var id: String { symbol }; let symbol: String; let price, volume24H: Decimal; let change24H, fundingRate, openInterest, riskScore: Decimal?; let timestamp: Date; let source: String; let isRealtime: Bool
}
struct Report: Identifiable, Equatable, Sendable { let id, title, type, markdown: String; let assets: [String]; let createdAt: Date }
struct BillingSummary: Equatable, Sendable { let plan, status: String; let credits: Int; let periodEnd: Date?; let cancelAtPeriodEnd: Bool; let availableSources: [String] }
struct AgentConversation: Identifiable, Equatable, Sendable { let id, title, status: String; let summary: String?; let createdAt, updatedAt: Date; let archivedAt: Date? }
struct AgentSource: Identifiable, Equatable, Sendable { let id, provider, title: String; let url: URL?; let publishedAt, sourceTimestamp, fetchedAt: Date?; let citationIndex: Int }
struct AgentMessage: Identifiable, Equatable, Sendable { let id, conversationID, role: String; var content, status: String; let model: String?; var sources: [AgentSource]; let createdAt: Date; var errorMessage: String? }
struct AgentModel: Identifiable, Equatable, Sendable { let id, name, details, provider: String; let available: Bool; let reason: String? }
struct AgentCapabilities: Equatable, Sendable { let plan: String; let dataSources: [String]; let dailyRuns, concurrentRuns, credits, remaining: Int; let models: [AgentModel] }
struct AgentAttachment: Identifiable, Equatable, Sendable { var id: String { name }; let name, content, mime: String }
struct AgentRequestContext: Equatable, Sendable { var dataSources = ["market", "rss"]; var skills = ["market_research", "news_research"]; var customPrompt = ""; var attachments: [AgentAttachment] = []; var model = "default" }
struct Portfolio: Equatable, Sendable { let connected, stale: Bool; let asOf: Date?; let nav, availableCash: Decimal?; let history: [NAVPoint]; let connections: [PortfolioConnection]; let providers: PortfolioProviders }
struct NAVPoint: Identifiable, Equatable, Sendable { var id: Date { date }; let date: Date; let value: Decimal }
struct PortfolioConnection: Identifiable, Equatable, Sendable { let id, provider, name, status: String; let lastSync: Date?; let error: String? }
struct PortfolioProviders: Equatable, Sendable { let plaid, ibkr, hyperliquid: Bool }
struct Autopilot: Equatable, Sendable { var enabled: Bool; var cadence: String; var autoSync, riskAlerts, longGammaWatch: Bool; var delivery: String; let accountCount: Int; let findings: [AutopilotFinding]; let lastReview: Date? }
struct AutopilotFinding: Equatable, Sendable { let severity, title: String }
struct OptionCandidate: Identifiable, Equatable, Sendable { var id: String { instrument }; let instrument, underlying, type: String; let strike, markIV, gamma, theta, score: Decimal?; let expiry, timestamp: Date; let rationale: [String] }
struct DailyPushPreference: Equatable, Sendable { var enabled: Bool; var timezone, localTime, channel, locale: String; var includePortfolio, includeMarket, includeSignals, includeRisk, includeSentiment: Bool; let nextDelivery: Date? }

enum PGFormat {
    static func money(_ value: Decimal?, currency: String = "USD") -> String { guard let value else { return "—" }; return value.formatted(.currency(code: currency).precision(.fractionLength(2))) }
    static func dateTime(_ value: Date?) -> String { guard let value else { return "—" }; return value.formatted(date: .abbreviated, time: .shortened) }
    static func percent(_ value: Decimal?) -> String { guard let value else { return "—" }; return "\(value >= 0 ? "+" : "")\(value.formatted(.number.precision(.fractionLength(2))))%" }
}
