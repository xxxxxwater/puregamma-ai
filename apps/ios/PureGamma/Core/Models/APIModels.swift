import Foundation

struct EmptyResponseDTO: Decodable { }
struct UserEnvelopeDTO: Decodable { let user: UserDTO }
struct UserDTO: Codable { let id, email, name, role, plan: String; let membershipTier: String?; let creditBalance: Int; let avatarURL: URL?; let locale: String?; enum CodingKeys: String, CodingKey { case id, email, name, role, plan, locale; case membershipTier = "membership_tier"; case creditBalance = "credit_balance"; case avatarURL = "avatar_url" }; var domain: User { User(id: id, email: email, name: name, role: role, plan: plan, membershipTier: membershipTier, creditBalance: creditBalance, avatarURL: avatarURL, locale: locale ?? "en") } }
struct MobileOAuthStartDTO: Encodable { let redirectURI, codeChallenge, clientState, nonce: String; enum CodingKeys: String, CodingKey { case nonce; case redirectURI = "redirect_uri"; case codeChallenge = "code_challenge"; case clientState = "client_state" } }
struct MobileOAuthStartResponseDTO: Decodable { let authURL: String; enum CodingKeys: String, CodingKey { case authURL = "auth_url" } }
struct MobileOAuthExchangeDTO: Encodable { let code, codeVerifier, nonce: String; enum CodingKeys: String, CodingKey { case code, nonce; case codeVerifier = "code_verifier" } }
struct MobileOAuthExchangeResponseDTO: Decodable { let accessToken: String; let user: UserDTO; enum CodingKeys: String, CodingKey { case user; case accessToken = "access_token" } }
struct MobileEmailLoginDTO: Encodable { let email, password: String }
struct MobileEmailRegisterDTO: Encodable { let email, password, name, locale: String }
struct AppleOAuthExchangeDTO: Encodable {
    let identityToken, authorizationCode, nonce: String
    let givenName, familyName: String?
    enum CodingKeys: String, CodingKey {
        case nonce
        case identityToken = "identity_token"
        case authorizationCode = "authorization_code"
        case givenName = "given_name"
        case familyName = "family_name"
    }
}

struct PushDeviceRequestDTO: Encodable {
    let token, environment, locale, timezone: String
}
struct PushDeviceRegistrationDTO: Decodable {
    let deliveryAvailable: Bool
    enum CodingKeys: String, CodingKey { case deliveryAvailable = "delivery_available" }
}
struct MobileIBKRStartDTO: Encodable {
    let redirectURI: String
    enum CodingKeys: String, CodingKey { case redirectURI = "redirect_uri" }
}
struct MobileIBKRCompleteDTO: Encodable { let code: String }

struct MarketEnvelopeDTO: Codable { let assets: [MarketAssetDTO] }
struct MarketAssetDTO: Codable { let symbol: String; let price, volume24H: Decimal; let change24H, fundingRate, openInterest, riskScore: Decimal?; let timestamp: Date; let sourceDisplay: String?; let source: String?; let isRealtime: Bool?; enum CodingKeys: String, CodingKey { case symbol, price, timestamp, source; case volume24H = "volume_24h"; case change24H = "change_24h"; case fundingRate = "funding_rate"; case openInterest = "open_interest"; case riskScore = "risk_score"; case sourceDisplay = "source_display"; case isRealtime = "is_realtime" }; var domain: MarketAsset { .init(symbol: symbol, price: price, volume24H: volume24H, change24H: change24H, fundingRate: fundingRate, openInterest: openInterest, riskScore: riskScore, timestamp: timestamp, source: sourceDisplay ?? source ?? "—", isRealtime: isRealtime ?? false) } }
struct ReportsEnvelopeDTO: Codable { let reports: [ReportDTO] }
struct ReportEnvelopeDTO: Decodable { let report: ReportDTO }
struct ReportDTO: Codable { let id, title, reportType, contentMarkdown: String; let assets: [String]; let createdAt: Date; enum CodingKeys: String, CodingKey { case id, title, assets; case reportType = "report_type"; case contentMarkdown = "content_markdown"; case createdAt = "created_at" }; var domain: Report { .init(id: id, title: title, type: reportType, markdown: contentMarkdown, assets: assets, createdAt: createdAt) } }
struct SubscriptionDTO: Decodable { let plan, subscriptionStatus: String; let membershipTier: String?; let creditBalance: Int; let currentPeriodEnd: Date?; let cancelAtPeriodEnd: Bool?; let entitlement: EntitlementDTO; enum CodingKeys: String, CodingKey { case plan, entitlement; case membershipTier = "membership_tier"; case subscriptionStatus = "subscription_status"; case creditBalance = "credit_balance"; case currentPeriodEnd = "current_period_end"; case cancelAtPeriodEnd = "cancel_at_period_end" } }
struct EntitlementDTO: Decodable { let allowedDataSources: [String]?; enum CodingKeys: String, CodingKey { case allowedDataSources = "allowed_data_sources" } }

struct ConversationEnvelopeDTO: Decodable { let conversation: ConversationDTO }
struct ConversationsEnvelopeDTO: Decodable { let conversations: [ConversationDTO] }
struct ConversationDetailDTO: Decodable { let conversation: ConversationDTO; let messages: [MessageDTO] }
struct ConversationDTO: Decodable { let id, title, status: String; let summary: String?; let createdAt, updatedAt: Date; let archivedAt: Date?; enum CodingKeys: String, CodingKey { case id, title, status, summary; case createdAt = "created_at"; case updatedAt = "updated_at"; case archivedAt = "archived_at" }; var domain: AgentConversation { .init(id: id, title: title, status: status, summary: summary, createdAt: createdAt, updatedAt: updatedAt, archivedAt: archivedAt) } }
struct MessageDTO: Decodable { let id, conversationID, role, content, status: String; let model: String?; let sources: [SourceDTO]; let createdAt: Date; let errorMessage: String?; enum CodingKeys: String, CodingKey { case id, role, content, status, model, sources; case conversationID = "conversation_id"; case createdAt = "created_at"; case errorMessage = "error_message" }; var domain: AgentMessage { .init(id: id, conversationID: conversationID, role: role, content: content, status: status, model: model, sources: sources.map(\.domain), createdAt: createdAt, errorMessage: errorMessage) } }
struct SourceDTO: Decodable { let id: String?; let provider, title: String; let url: URL?; let publishedAt, sourceTimestamp, fetchedAt: Date?; let citationIndex: Int; enum CodingKeys: String, CodingKey { case id, provider, title, url; case publishedAt = "published_at"; case sourceTimestamp = "source_timestamp"; case fetchedAt = "fetched_at"; case citationIndex = "citation_index" }; var domain: AgentSource { .init(id: id ?? "\(citationIndex)-\(provider)", provider: provider, title: title, url: url, publishedAt: publishedAt, sourceTimestamp: sourceTimestamp, fetchedAt: fetchedAt, citationIndex: citationIndex) } }
struct CapabilitiesEnvelopeDTO: Decodable { let capabilities: CapabilitiesDTO; let quota: QuotaDTO; let models: [ModelDTO]; let skills: [SkillDTO]? }
struct SkillDTO: Decodable { let slug, name: String; let description: String? }
struct CapabilitiesDTO: Decodable { let plan: String; let allowedDataSources: [String]; let agentDailyRuns, agentConcurrentRuns: Int; enum CodingKeys: String, CodingKey { case plan; case allowedDataSources = "allowed_data_sources"; case agentDailyRuns = "agent_daily_runs"; case agentConcurrentRuns = "agent_concurrent_runs" } }
struct QuotaDTO: Decodable { let remaining, creditBalance: Int; enum CodingKeys: String, CodingKey { case remaining; case creditBalance = "credit_balance" } }
struct ModelDTO: Decodable { let id, displayName, description, provider: String; let available: Bool; let reason: String?; enum CodingKeys: String, CodingKey { case id, description, provider, available, reason; case displayName = "display_name" } }

struct PortfolioDTO: Codable { let connected: Bool; let stale: Bool?; let dataAsOf: Date?; let nav, availableCash: Decimal?; let navHistory: [NAVPointDTO]; let connections: [PortfolioConnectionDTO]; let providers: PortfolioProvidersDTO; enum CodingKeys: String, CodingKey { case connected, stale, nav, connections, providers; case dataAsOf = "data_as_of"; case availableCash = "available_cash"; case navHistory = "nav_history" }; var domain: Portfolio { .init(connected: connected, stale: stale ?? false, asOf: dataAsOf, nav: connected ? nav : nil, availableCash: connected ? availableCash : nil, history: navHistory.map(\.domain), connections: connections.map(\.domain), providers: providers.domain) } }
struct NAVPointDTO: Codable { let date: Date; let nav: Decimal; var domain: NAVPoint { .init(date: date, value: nav) } }
struct PortfolioConnectionDTO: Codable { let id, provider, name, status: String; let lastSync: Date?; let error: String?; enum CodingKeys: String, CodingKey { case id, provider, name, status, error; case lastSync = "last_sync" }; var domain: PortfolioConnection { .init(id: id, provider: provider, name: name, status: status, lastSync: lastSync, error: error) } }
struct PortfolioProvidersDTO: Codable { let plaid, ibkr, hyperliquid: Bool; var domain: PortfolioProviders { .init(plaid: plaid, ibkr: ibkr, hyperliquid: hyperliquid) } }
struct LinkTokenDTO: Decodable { let linkToken: String; enum CodingKeys: String, CodingKey { case linkToken = "link_token" } }
struct URLDTO: Decodable { let authorizeURL: URL; enum CodingKeys: String, CodingKey { case authorizeURL = "authorize_url" } }
struct AutopilotDTO: Decodable { let config: AutopilotConfigDTO; let accountCount: Int; let findings: [AutopilotFindingDTO]; let lastReview: Date?; enum CodingKeys: String, CodingKey { case config, findings; case accountCount = "account_count"; case lastReview = "last_review" }; var domain: Autopilot { .init(enabled: config.enabled, cadence: config.cadence, autoSync: config.autoSync, riskAlerts: config.riskAlerts, longGammaWatch: config.longGammaWatch, delivery: config.delivery, accountCount: accountCount, findings: findings.map { .init(severity: $0.severity, title: $0.title) }, lastReview: lastReview) } }
struct AutopilotConfigDTO: Codable { var enabled: Bool; var cadence: String; var autoSync, riskAlerts, longGammaWatch: Bool; var delivery: String; enum CodingKeys: String, CodingKey { case enabled, cadence, delivery; case autoSync = "auto_sync"; case riskAlerts = "risk_alerts"; case longGammaWatch = "long_gamma_watch" } }
struct AutopilotFindingDTO: Decodable { let severity, title: String }

struct LongGammaEnvelopeDTO: Decodable { let status, provider, currency: String; let fetchedAt: Date?; let candidates: [OptionCandidateDTO]; let error: String?; enum CodingKeys: String, CodingKey { case status, provider, currency, candidates, error; case fetchedAt = "fetched_at" } }
struct OptionCandidateDTO: Decodable { let instrument, underlying, optionType: String; let strike, markIV: Decimal?; let expiry, timestamp: Date; let greeks: GreeksDTO; let researchScore: Decimal?; let rationale: [String]; enum CodingKeys: String, CodingKey { case instrument, underlying, strike, expiry, timestamp, greeks, rationale; case optionType = "option_type"; case markIV = "mark_iv"; case researchScore = "research_score" }; var domain: OptionCandidate { .init(instrument: instrument, underlying: underlying, type: optionType, strike: strike, markIV: markIV, gamma: greeks.gamma, theta: greeks.theta, score: researchScore, expiry: expiry, timestamp: timestamp, rationale: rationale) } }
struct GreeksDTO: Decodable { let gamma, theta: Decimal? }

struct DailyPushEnvelopeDTO: Decodable { let preference: DailyPushDTO }
struct DailyPushDTO: Codable { var enabled: Bool; var timezone, localTime, channel, locale: String; var includePortfolio, includeMarket, includeSignals, includeRisk, includeSentiment: Bool; let nextDeliveryAt: Date?; enum CodingKeys: String, CodingKey { case enabled, timezone, channel, locale; case localTime = "local_time"; case includePortfolio = "include_portfolio"; case includeMarket = "include_market"; case includeSignals = "include_signals"; case includeRisk = "include_risk"; case includeSentiment = "include_sentiment"; case nextDeliveryAt = "next_delivery_at" }; var domain: DailyPushPreference { .init(enabled: enabled, timezone: timezone, localTime: localTime, channel: channel, locale: locale, includePortfolio: includePortfolio, includeMarket: includeMarket, includeSignals: includeSignals, includeRisk: includeRisk, includeSentiment: includeSentiment, nextDelivery: nextDeliveryAt) } }

struct SignalsEnvelopeDTO: Decodable { let signals: [SignalDTO] }
struct SignalDTO: Decodable { let id, asset, signalType, direction: String; let confidence, riskScore: Decimal?; let thesis, catalyst, invalidation, timeframe: String?; let createdAt: Date; enum CodingKeys: String, CodingKey { case id, asset, direction, thesis, catalyst, invalidation, timeframe, confidence; case signalType = "signal_type"; case riskScore = "risk_score"; case createdAt = "created_at" }; var domain: Signal { .init(id: id, asset: asset, signalType: signalType, direction: direction, confidence: confidence, riskScore: riskScore, thesis: thesis, catalyst: catalyst, invalidation: invalidation, timeframe: timeframe, createdAt: createdAt) } }

struct PlaybooksEnvelopeDTO: Decodable { let playbooks: [PlaybookDTO]; let reports: [ReportDTO]? }
struct PlaybookDTO: Decodable { let strategyName, asset, thesis, trigger, entryCondition, exitCondition, invalidation, timeframe, expectedPayoff: String; let riskScore: Int; let confidence: Decimal; let requiredDataSources: [String]; enum CodingKeys: String, CodingKey { case asset, thesis, trigger, invalidation, timeframe, confidence; case strategyName = "strategy_name"; case entryCondition = "entry_condition"; case exitCondition = "exit_condition"; case riskScore = "risk_score"; case expectedPayoff = "expected_payoff"; case requiredDataSources = "required_data_sources" }; var domain: Playbook { .init(strategyName: strategyName, asset: asset, thesis: thesis, trigger: trigger, entryCondition: entryCondition, exitCondition: exitCondition, invalidation: invalidation, riskScore: riskScore, confidence: confidence, timeframe: timeframe, expectedPayoff: expectedPayoff, requiredDataSources: requiredDataSources) } }

struct BacktestStatusDTO: Decodable { let symbols: [String]; let coverage: [String: Decimal]?; let lastRefresh: Date?; enum CodingKeys: String, CodingKey { case symbols, coverage; case lastRefresh = "last_refresh" } }
struct BacktestRunRequestDTO: Encodable { let spec: BacktestSpecDTO; let windowDays: Int; enum CodingKeys: String, CodingKey { case spec; case windowDays = "window_days" } }
struct BacktestSpecDTO: Encodable { let name, mode, signal: String; let assets: [String]; let fastWindow, slowWindow: Int; let rebalanceDays: Int; let longShort: Bool; let maxPosition, feeBps: Double; enum CodingKeys: String, CodingKey { case name, mode, signal, assets; case fastWindow = "fast_window"; case slowWindow = "slow_window"; case rebalanceDays = "rebalance_days"; case longShort = "long_short"; case maxPosition = "max_position"; case feeBps = "fee_bps" } }
struct BacktestRunsEnvelopeDTO: Decodable { let runs: [BacktestRunDTO]; let limit: Int?; let offset: Int? }
struct BacktestRunEnvelopeDTO: Decodable { let run: BacktestRunDTO }
struct BacktestRunDTO: Decodable {
    let id, status, mode, strategyName, asset: String
    let spec: [String: String]?
    let windowStart, windowEnd: String?
    let metrics: [String: Decimal]?
    let equityCurve, drawdownCurve, benchmarkCurve: [EquityPointDTO]?
    let trades: [BacktestTradeDTO]?
    let positions: [String]?
    let error: [String: String]?
    let creditsSpent: Decimal?
    let createdAt, completedAt: String?
    enum CodingKeys: String, CodingKey { case id, status, mode, spec, asset, trades, positions, error, metrics; case strategyName = "strategy_name"; case windowStart = "window_start"; case windowEnd = "window_end"; case equityCurve = "equity_curve"; case drawdownCurve = "drawdown_curve"; case benchmarkCurve = "benchmark_curve"; case creditsSpent = "credits_spent"; case createdAt = "created_at"; case completedAt = "completed_at" }
    var domain: BacktestRun {
        func points(_ rows: [EquityPointDTO]?) -> [BacktestPoint] { (rows ?? []).enumerated().map { .init(index: $0.offset, value: $0.element.value) } }
        func date(_ raw: String?) -> Date? { raw.flatMap { parseUTCDate($0) } }
        return .init(id: id, status: status, mode: mode, strategyName: strategyName, asset: asset, spec: spec ?? [:], windowStart: date(windowStart), windowEnd: date(windowEnd), metrics: metrics ?? [:], equityCurve: points(equityCurve), drawdownCurve: points(drawdownCurve), benchmarkCurve: points(benchmarkCurve), trades: (trades ?? []).map { .init(asset: $0.asset, side: $0.side, quantity: $0.quantity, price: $0.price, pnl: $0.pnl) }, positions: positions ?? [], error: error ?? [:], creditsSpent: creditsSpent, createdAt: date(createdAt), completedAt: date(completedAt))
    }
}
struct EquityPointDTO: Decodable { let value: Decimal; let ts: Date? }
struct BacktestTradeDTO: Decodable { let asset, side: String; let quantity, price, pnl: Decimal? }
struct AgentQuoteDTO: Decodable { let estimatedMin, estimatedMax, reservationAmount: Int; enum CodingKeys: String, CodingKey { case estimatedMin = "estimated_min"; case estimatedMax = "estimated_max"; case reservationAmount = "reservation_amount" } }
struct AgentQuoteRequestDTO: Encodable { let content, researchMode: String?; enum CodingKeys: String, CodingKey { case content; case researchMode = "research_mode" } }
