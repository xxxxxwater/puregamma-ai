import Foundation

private func parseUTCDate(_ raw: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let standard = ISO8601DateFormatter()
    standard.formatOptions = [.withInternetDateTime]
    return fractional.date(from: raw) ?? standard.date(from: raw)
}

struct RepositoryContainer {
    let today: TodayRepository; let agent: AgentRepository; let research: ResearchRepository; let portfolio: PortfolioRepository; let account: AccountRepository
    private let responseCache: ResponseCache
    @MainActor init(client: APIClient) { let cache = ResponseCache(); responseCache = cache; today = TodayRepository(client: client, cache: cache); agent = AgentRepository(client: client); research = ResearchRepository(client: client, cache: cache); portfolio = PortfolioRepository(client: client, cache: cache); account = AccountRepository(client: client) }
    func clearCaches() async { try? await responseCache.clear() }
}

@MainActor struct TodayRepository {
    let client: APIClient; let cache: ResponseCache
    func market() async throws -> [MarketAsset] { let dto: MarketEnvelopeDTO = try await client.request("/market/snapshot"); return dto.assets.map(\.domain) }
    func reports() async throws -> [Report] { let dto: ReportsEnvelopeDTO = try await client.request("/reports"); return dto.reports.map(\.domain) }
    func cachedMarket() async throws -> CachedRepositoryValue<[MarketAsset]> {
        do { let dto: MarketEnvelopeDTO = try await client.request("/market/snapshot"); try? await cache.save(dto, key: "market-snapshot"); return .init(value: dto.assets.map(\.domain), cachedAt: nil) }
        catch { if canUseCache(error), let cached = try? await cache.load(MarketEnvelopeDTO.self, key: "market-snapshot", maximumAge: 86_400) { return .init(value: cached.0.assets.map(\.domain), cachedAt: cached.1) }; throw error }
    }
    func cachedReports() async throws -> CachedRepositoryValue<[Report]> {
        do { let dto: ReportsEnvelopeDTO = try await client.request("/reports"); try? await cache.save(dto, key: "reports"); return .init(value: dto.reports.map(\.domain), cachedAt: nil) }
        catch { if canUseCache(error), let cached = try? await cache.load(ReportsEnvelopeDTO.self, key: "reports", maximumAge: 604_800) { return .init(value: cached.0.reports.map(\.domain), cachedAt: cached.1) }; throw error }
    }
    func subscription() async throws -> BillingSummary { let dto: SubscriptionDTO = try await client.request("/billing/subscription"); return .init(plan: dto.plan, status: dto.subscriptionStatus, credits: dto.creditBalance, periodEnd: dto.currentPeriodEnd, cancelAtPeriodEnd: dto.cancelAtPeriodEnd ?? false, availableSources: dto.entitlement.allowedDataSources ?? []) }
}

@MainActor struct AgentRepository {
    let client: APIClient
    func conversations() async throws -> [AgentConversation] { let dto: ConversationsEnvelopeDTO = try await client.request("/api/agent/conversations"); return dto.conversations.map(\.domain) }
    func create(title: String? = nil) async throws -> AgentConversation { let dto: ConversationEnvelopeDTO = try await client.request("/api/agent/conversations", method: "POST", body: ["title": title]); return dto.conversation.domain }
    func conversation(_ id: String) async throws -> (AgentConversation, [AgentMessage]) { let dto: ConversationDetailDTO = try await client.request("/api/agent/conversations/\(id)"); return (dto.conversation.domain, dto.messages.map(\.domain)) }
    func update(_ id: String, title: String? = nil, archived: Bool? = nil) async throws -> AgentConversation { let dto: ConversationEnvelopeDTO = try await client.request("/api/agent/conversations/\(id)", method: "PATCH", body: ConversationPatchDTO(title: title, archived: archived)); return dto.conversation.domain }
    func delete(_ id: String) async throws { let _: EmptyResponseDTO = try await client.request("/api/agent/conversations/\(id)", method: "DELETE") }
    func capabilities() async throws -> AgentCapabilities { let dto: CapabilitiesEnvelopeDTO = try await client.request("/api/agent/capabilities"); return .init(plan: dto.capabilities.plan, dataSources: dto.capabilities.allowedDataSources, dailyRuns: dto.capabilities.agentDailyRuns, concurrentRuns: dto.capabilities.agentConcurrentRuns, credits: dto.quota.creditBalance, remaining: dto.quota.remaining, models: dto.models.map { .init(id: $0.id, name: $0.displayName, details: $0.description, provider: $0.provider, available: $0.available, reason: $0.reason) }) }
    func stream(conversationID: String, prompt: String, locale: String, context: AgentRequestContext) async throws -> AsyncThrowingStream<AgentSSEEvent, Error> {
        let payload = AgentMessageRequestDTO(content: prompt, locale: locale, dataSources: context.dataSources, skills: context.skills, customPrompt: context.customPrompt, attachments: context.attachments.map { .init(name: $0.name, content: $0.content, mime: $0.mime) }, model: context.model)
        let (bytes, _) = try await client.stream("/api/agent/conversations/\(conversationID)/messages", body: payload)
        return AsyncThrowingStream { continuation in
            let task = Task { do { var parser = SSEParser(); for try await line in bytes.lines { if let event = parser.consume(line) { continuation.yield(try AgentSSEEvent.decode(event)); } }; continuation.finish() } catch { continuation.finish(throwing: error) } }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
    func cancel(runID: String) async throws { let _: EmptyResponseDTO = try await client.request("/api/agent/runs/\(runID)/cancel", method: "POST") }
}
struct ConversationPatchDTO: Encodable { let title: String?; let archived: Bool? }
struct AgentAttachmentDTO: Encodable { let name, content, mime: String }
struct AgentMessageRequestDTO: Encodable { let content, locale: String; let dataSources, skills: [String]; let customPrompt: String; let attachments: [AgentAttachmentDTO]; let model: String; enum CodingKeys: String, CodingKey { case content, locale, skills, attachments, model; case dataSources = "data_sources"; case customPrompt = "custom_prompt" } }

enum AgentSSEEvent: Equatable, Sendable {
    case runStarted(String), delta(String), toolStarted(String), toolCompleted(String), citation(AgentSource), completed, failed(String), canceled
    static func decode(_ event: ServerSentEvent) throws -> AgentSSEEvent {
        let object = (try JSONSerialization.jsonObject(with: event.data) as? [String: Any]) ?? [:]
        func string(_ keys: String...) -> String { keys.compactMap { object[$0] as? String }.first ?? "" }
        switch event.event {
        case "run.started": return .runStarted(string("runId", "run_id", "id"))
        case "message.delta": return .delta(string("delta", "content"))
        case "tool.started": return .toolStarted(string("tool", "name"))
        case "tool.completed": return .toolCompleted(string("tool", "name"))
        case "citation":
            let index = object["index"] as? Int ?? 0
            let published = (object["publishedAt"] as? String).flatMap(parseUTCDate)
            let sourceTime = (object["sourceTimestamp"] as? String).flatMap(parseUTCDate)
            let fetched = (object["fetchedAt"] as? String).flatMap(parseUTCDate)
            return .citation(.init(id: "\(index)-\(string("provider"))", provider: string("provider"), title: string("title"), url: URL(string: string("url")), publishedAt: published, sourceTimestamp: sourceTime, fetchedAt: fetched, citationIndex: index))
        case "message.completed": return .completed
        case "run.failed": return .failed(string("message", "error", "code"))
        case "run.canceled": return .canceled
        default: throw APIError.decoding("Unknown SSE event \(event.event)")
        }
    }
}

@MainActor struct ResearchRepository {
    let client: APIClient; let cache: ResponseCache
    func reports() async throws -> [Report] { let dto: ReportsEnvelopeDTO = try await client.request("/reports"); return dto.reports.map(\.domain) }
    func cachedReports() async throws -> CachedRepositoryValue<[Report]> { try await TodayRepository(client: client, cache: cache).cachedReports() }
    func longGamma(currency: String) async throws -> (String, Date?, [OptionCandidate], String?) { let dto: LongGammaEnvelopeDTO = try await client.request("/options/long-gamma", query: [URLQueryItem(name: "currency", value: currency)]); return (dto.status, dto.fetchedAt, dto.candidates.map(\.domain), dto.error) }
}

@MainActor struct PortfolioRepository {
    let client: APIClient; let cache: ResponseCache
    func snapshot() async throws -> Portfolio { let dto: PortfolioDTO = try await client.request("/portfolio"); return dto.domain }
    func cachedSnapshot() async throws -> CachedRepositoryValue<Portfolio> {
        do { let dto: PortfolioDTO = try await client.request("/portfolio"); try? await cache.save(dto, key: "portfolio"); return .init(value: dto.domain, cachedAt: nil) }
        catch { if canUseCache(error), let cached = try? await cache.load(PortfolioDTO.self, key: "portfolio", maximumAge: 86_400) { return .init(value: cached.0.domain, cachedAt: cached.1) }; throw error }
    }
    func plaidLinkToken() async throws -> String { let dto: LinkTokenDTO = try await client.request("/portfolio/plaid/link-token", method: "POST"); return dto.linkToken }
    func exchangePlaid(publicToken: String, institution: String) async throws -> Portfolio { let dto: PortfolioDTO = try await client.request("/portfolio/plaid/exchange", method: "POST", body: ["public_token": publicToken, "institution_name": institution]); return dto.domain }
    func ibkrMobileURL(redirectURI: String) async throws -> URL { let dto: URLDTO = try await client.request("/portfolio/ibkr/mobile/start", method: "POST", body: MobileIBKRStartDTO(redirectURI: redirectURI)); return dto.authorizeURL }
    func completeIBKR(code: String) async throws -> Portfolio { let dto: PortfolioDTO = try await client.request("/portfolio/ibkr/mobile/complete", method: "POST", body: MobileIBKRCompleteDTO(code: code)); return dto.domain }
    func connectHyperliquid(address: String) async throws -> Portfolio { let dto: PortfolioDTO = try await client.request("/portfolio/hyperliquid/connect", method: "POST", body: ["address": address]); return dto.domain }
    func sync(_ id: String) async throws -> Portfolio { let dto: PortfolioDTO = try await client.request("/portfolio/accounts/\(id)/sync", method: "POST"); return dto.domain }
    func disconnect(_ id: String) async throws -> Portfolio { let dto: PortfolioDTO = try await client.request("/portfolio/accounts/\(id)", method: "DELETE"); return dto.domain }
    func autopilot() async throws -> Autopilot { let dto: AutopilotDTO = try await client.request("/portfolio/autopilot"); return dto.domain }
    func updateAutopilot(_ config: AutopilotConfigDTO) async throws -> Autopilot { let dto: AutopilotDTO = try await client.request("/portfolio/autopilot", method: "PUT", body: config); return dto.domain }
    func runAutopilot() async throws -> Autopilot { let dto: AutopilotDTO = try await client.request("/portfolio/autopilot/run", method: "POST"); return dto.domain }
}

private func canUseCache(_ error: Error) -> Bool {
    guard let apiError = error as? APIError else { return false }
    switch apiError {
    case .transport, .unavailable: return true
    case .server(let status, _): return status >= 500
    default: return false
    }
}

@MainActor struct AccountRepository {
    let client: APIClient
    func subscription() async throws -> BillingSummary { let dto: SubscriptionDTO = try await client.request("/billing/subscription"); return .init(plan: dto.plan, status: dto.subscriptionStatus, credits: dto.creditBalance, periodEnd: dto.currentPeriodEnd, cancelAtPeriodEnd: dto.cancelAtPeriodEnd ?? false, availableSources: dto.entitlement.allowedDataSources ?? []) }
    func pushPreference() async throws -> DailyPushPreference { let dto: DailyPushEnvelopeDTO = try await client.request("/notifications/preferences/daily-brief"); return dto.preference.domain }
    func updatePush(_ value: DailyPushPreference) async throws -> DailyPushPreference { let body = DailyPushDTO(enabled: value.enabled, timezone: value.timezone, localTime: value.localTime, channel: value.channel, locale: value.locale, includePortfolio: value.includePortfolio, includeMarket: value.includeMarket, includeSignals: value.includeSignals, includeRisk: value.includeRisk, includeSentiment: value.includeSentiment, nextDeliveryAt: value.nextDelivery); let dto: DailyPushEnvelopeDTO = try await client.request("/notifications/preferences/daily-brief", method: "PUT", body: body); return dto.preference.domain }
    func registerPushDevice(token: String) async throws -> Bool {
        #if DEBUG
        let environment = "sandbox"
        #else
        let environment = "production"
        #endif
        let body = PushDeviceRequestDTO(token: token, environment: environment, locale: Locale.current.identifier, timezone: TimeZone.current.identifier)
        let dto: PushDeviceRegistrationDTO = try await client.request("/notifications/devices", method: "POST", body: body)
        return dto.deliveryAvailable
    }
    func unregisterPushDevice(token: String) async throws { let body = PushDeviceRequestDTO(token: token, environment: "production", locale: Locale.current.identifier, timezone: TimeZone.current.identifier); let _: EmptyResponseDTO = try await client.request("/notifications/devices/unregister", method: "POST", body: body) }
    func deleteAccount(confirmation: String) async throws { let _: EmptyResponseDTO = try await client.request("/me", method: "DELETE", body: ["confirmation": confirmation]) }
}
