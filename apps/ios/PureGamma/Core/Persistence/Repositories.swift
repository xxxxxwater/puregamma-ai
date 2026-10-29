import Foundation

/// ISO-8601 instants from the API. Production rows carry an offset; a naive
/// value (no `Z`/offset, as some stores return) is read as UTC rather than
/// rejected, so one missing suffix cannot fail a whole response.
func parseUTCDate(_ raw: String) -> Date? {
    let fractional = ISO8601DateFormatter()
    fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let standard = ISO8601DateFormatter()
    standard.formatOptions = [.withInternetDateTime]
    if let date = fractional.date(from: raw) ?? standard.date(from: raw) { return date }
    guard raw.range(of: #"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?$"#, options: .regularExpression) != nil else { return nil }
    return fractional.date(from: raw + "Z") ?? standard.date(from: raw + "Z")
}

struct RepositoryContainer {
    let today: TodayRepository; let agent: AgentRepository; let research: ResearchRepository; let portfolio: PortfolioRepository; let account: AccountRepository
    let mobileCapabilities: MobileCapabilitiesRepository; let researchRuns: ResearchRunsRepository; let memory: MemoryRepository; let tradingMandates: TradingMandatesRepository
    let liveNav: LiveNavRepository
    /// Repository 层能力门控的唯一事实来源（AppState 在登录/注销时更新）。
    let capabilitiesStore: MobileCapabilitiesStore
    private let responseCache: ResponseCache
    private let environment: String

    @MainActor init(client: APIClient) {
        let cache = ResponseCache()
        responseCache = cache
        let store = MobileCapabilitiesStore()
        capabilitiesStore = store
        environment = client.configuration.environment
        today = TodayRepository(client: client, cache: cache)
        agent = AgentRepository(client: client)
        research = ResearchRepository(client: client, cache: cache)
        portfolio = PortfolioRepository(client: client, cache: cache)
        account = AccountRepository(client: client)
        mobileCapabilities = MobileCapabilitiesRepository(client: client)
        researchRuns = ResearchRunsRepository(client: client, cache: cache, gate: store)
        memory = MemoryRepository(client: client, gate: store)
        tradingMandates = TradingMandatesRepository(client: client, gate: store)
        liveNav = LiveNavRepository(client: client)
    }

    /// 登录成功后按用户命名缓存，避免同设备多账号读到彼此的 stale 数据。
    /// 格式：`{environment}:{user_id}:{key}`。
    func setCacheNamespace(userID: String) async {
        await responseCache.setNamespace("\(environment):\(userID)")
    }

    /// 注销/401/删除账户：重置命名空间并清空全部缓存（当前用户所有移动端缓存）。
    func clearCaches() async {
        await responseCache.setNamespace(nil)
        try? await responseCache.clear()
    }
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
    func subscription() async throws -> BillingSummary { let dto: SubscriptionDTO = try await client.request("/billing/subscription"); return .init(plan: dto.plan, status: dto.subscriptionStatus, membershipTier: dto.membershipTier, credits: dto.creditBalance, periodEnd: dto.currentPeriodEnd, cancelAtPeriodEnd: dto.cancelAtPeriodEnd ?? false, availableSources: dto.entitlement.allowedDataSources ?? []) }
}

@MainActor struct AgentRepository {
    let client: APIClient
    func conversations() async throws -> [AgentConversation] { let dto: ConversationsEnvelopeDTO = try await client.request("/api/agent/conversations"); return dto.conversations.map(\.domain) }
    func create(title: String? = nil) async throws -> AgentConversation { let dto: ConversationEnvelopeDTO = try await client.request("/api/agent/conversations", method: "POST", body: ["title": title]); return dto.conversation.domain }
    func conversation(_ id: String) async throws -> (AgentConversation, [AgentMessage]) { let snapshot = try await snapshot(id); return (snapshot.conversation, snapshot.messages) }
    /// The conversation with the run the server is still producing, if any (§8.6).
    func snapshot(_ id: String) async throws -> AgentConversationSnapshot { let dto: ConversationDetailDTO = try await client.request("/api/agent/conversations/\(id)"); return dto.snapshot }
    func update(_ id: String, title: String? = nil, archived: Bool? = nil) async throws -> AgentConversation { let dto: ConversationEnvelopeDTO = try await client.request("/api/agent/conversations/\(id)", method: "PATCH", body: ConversationPatchDTO(title: title, archived: archived)); return dto.conversation.domain }
    func setPermission(_ id: String, mode: AgentPermissionMode) async throws -> AgentConversation { let dto: ConversationEnvelopeDTO = try await client.request("/api/agent/conversations/\(id)", method: "PATCH", body: ["permission_mode": mode.rawValue]); return dto.conversation.domain }
    func delete(_ id: String) async throws { let _: EmptyResponseDTO = try await client.request("/api/agent/conversations/\(id)", method: "DELETE") }
    func capabilities() async throws -> AgentCapabilities { let dto: CapabilitiesEnvelopeDTO = try await client.request("/api/agent/capabilities"); return .init(plan: dto.capabilities.plan, dataSources: dto.capabilities.allowedDataSources, dailyRuns: dto.capabilities.agentDailyRuns, concurrentRuns: dto.capabilities.agentConcurrentRuns, credits: dto.quota.creditBalance, remaining: dto.quota.remaining, models: dto.models.map(\.domain), skills: (dto.skills ?? []).map(\.slug)) }
    func workspaceCapabilities() async throws -> AgentWorkspaceCapabilitiesDTO { try await client.request("/api/agent/workspace-capabilities") }
    /// Opens the send stream. Coded refusals arrive as `APIError.rejected` so a
    /// 409 keeps the `runId` of the run this attempt already started.
    func stream(conversationID: String, prompt: String, locale: String, context: AgentRequestContext, clientRequestID: String) async throws -> AsyncThrowingStream<AgentStreamFrame, Error> {
        let payload = AgentMessageRequestDTO(content: prompt, locale: locale, dataSources: context.dataSources, skills: context.skills, customPrompt: context.customPrompt, attachments: context.attachments.map { .init(name: $0.name, content: $0.content, mime: $0.mime) }, model: context.model, clientRequestID: clientRequestID)
        let (bytes, _) = try await client.stream("/api/agent/conversations/\(conversationID)/messages", body: payload, codedErrors: true)
        return AsyncThrowingStream { continuation in
            let task = Task { do { var parser = SSEParser(); for try await line in bytes.lines { if let event = parser.consume(line) { continuation.yield(AgentStreamFrame.decode(event)) } }; if let last = parser.finish() { continuation.yield(AgentStreamFrame.decode(last)) }; continuation.finish() } catch { continuation.finish(throwing: error) } }
            continuation.onTermination = { _ in task.cancel() }
        }
    }
    func runEvents(runID: String, after: Int) async throws -> AgentRunEventsPage {
        let data = try await client.requestData("/api/agent/runs/\(runID)/events", query: [URLQueryItem(name: "after", value: String(after))])
        return try AgentRunEventsPage.parse(data)
    }
    func cancel(runID: String) async throws { let _: EmptyResponseDTO = try await client.request("/api/agent/runs/\(runID)/cancel", method: "POST") }
}
struct ConversationPatchDTO: Encodable { let title: String?; let archived: Bool? }
struct AgentAttachmentDTO: Encodable { let name, content, mime: String }
struct AgentMessageRequestDTO: Encodable { let content, locale: String; let dataSources, skills: [String]; let customPrompt: String; let attachments: [AgentAttachmentDTO]; let model: String; let clientRequestID: String; enum CodingKeys: String, CodingKey { case content, locale, skills, attachments, model; case dataSources = "data_sources"; case customPrompt = "custom_prompt"; case clientRequestID = "client_request_id" } }

@MainActor struct ResearchRepository {
    let client: APIClient; let cache: ResponseCache
    func reports() async throws -> [Report] { let dto: ReportsEnvelopeDTO = try await client.request("/reports"); return dto.reports.map(\.domain) }
    func cachedReports() async throws -> CachedRepositoryValue<[Report]> { try await TodayRepository(client: client, cache: cache).cachedReports() }
    func generateDailyReport() async throws -> Report { let dto: ReportEnvelopeDTO = try await client.request("/reports/daily", method: "POST"); return dto.report.domain }
    func longGamma(currency: String) async throws -> (String, Date?, [OptionCandidate], String?) { let dto: LongGammaEnvelopeDTO = try await client.request("/options/long-gamma", query: [URLQueryItem(name: "currency", value: currency)]); return (dto.status, dto.fetchedAt, dto.candidates.map(\.domain), dto.error) }
    func signals() async throws -> [Signal] { let dto: SignalsEnvelopeDTO = try await client.request("/signals"); return dto.signals.map(\.domain) }
    func playbooks() async throws -> (playbooks: [Playbook], reports: [Report]) { let dto: PlaybooksEnvelopeDTO = try await client.request("/playbooks"); return (dto.playbooks.map(\.domain), dto.reports?.map(\.domain) ?? []) }
    func generatePlaybook() async throws -> [Playbook] { let dto: PlaybooksEnvelopeDTO = try await client.request("/playbooks/generate", method: "POST"); return dto.playbooks.map(\.domain) }
    func backtestStatus() async throws -> BacktestStatusDTO { try await client.request("/backtest-lab/status") }
    func runBacktest(spec: BacktestSpecDTO, windowDays: Int) async throws -> BacktestRun { let dto: BacktestRunEnvelopeDTO = try await client.request("/backtest-lab/runs", method: "POST", body: BacktestRunRequestDTO(spec: spec, windowDays: windowDays)); return dto.run.domain }
    func backtestRuns() async throws -> [BacktestRun] { let dto: BacktestRunsEnvelopeDTO = try await client.request("/backtest-lab/runs"); return dto.runs.map(\.domain) }
    func backtestRun(_ id: String) async throws -> BacktestRun { let dto: BacktestRunEnvelopeDTO = try await client.request("/backtest-lab/runs/\(id)"); return dto.run.domain }
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

/// Server-computed LIVE NAV (§8.3). No account is a state, not an error, and
/// it is never shown as a zero NAV.
@MainActor struct LiveNavRepository {
    let client: APIClient
    func current() async throws -> LiveNavState {
        do {
            let dto: LiveNavEnvelopeDTO = try await client.request("/api/portfolio/nav")
            return .loaded(dto.domain)
        } catch let error as APIError where LiveNavState.isNoAccount(error) {
            return .noAccount
        }
    }
    func history(limit: Int = 100) async throws -> [LiveNav] {
        let dto: LiveNavHistoryDTO = try await client.request("/api/portfolio/nav/history", query: [URLQueryItem(name: "limit", value: String(limit))])
        return dto.history.map(\.domain)
    }
}

func canUseCache(_ error: Error) -> Bool {
    guard let apiError = error as? APIError else { return false }
    switch apiError {
    case .transport, .unavailable: return true
    case .server(let status, _): return status >= 500
    default: return false
    }
}

@MainActor struct AccountRepository {
    let client: APIClient
    private static var pushEnvironment: String {
        #if DEBUG
        "sandbox"
        #else
        "production"
        #endif
    }
    func subscription() async throws -> BillingSummary { let dto: SubscriptionDTO = try await client.request("/billing/subscription"); return .init(plan: dto.plan, status: dto.subscriptionStatus, membershipTier: dto.membershipTier, credits: dto.creditBalance, periodEnd: dto.currentPeriodEnd, cancelAtPeriodEnd: dto.cancelAtPeriodEnd ?? false, availableSources: dto.entitlement.allowedDataSources ?? []) }
    func pushPreference() async throws -> DailyPushPreference { let dto: DailyPushEnvelopeDTO = try await client.request("/notifications/preferences/daily-brief"); return dto.preference.domain }
    func updatePush(_ value: DailyPushPreference) async throws -> DailyPushPreference { let body = DailyPushDTO(enabled: value.enabled, timezone: value.timezone, localTime: value.localTime, channel: value.channel, locale: value.locale, includePortfolio: value.includePortfolio, includeMarket: value.includeMarket, includeSignals: value.includeSignals, includeRisk: value.includeRisk, includeSentiment: value.includeSentiment, nextDeliveryAt: value.nextDelivery); let dto: DailyPushEnvelopeDTO = try await client.request("/notifications/preferences/daily-brief", method: "PUT", body: body); return dto.preference.domain }
    func registerPushDevice(token: String) async throws -> Bool {
        let body = PushDeviceRequestDTO(token: token, environment: Self.pushEnvironment, locale: Locale.current.identifier, timezone: TimeZone.current.identifier)
        let dto: PushDeviceRegistrationDTO = try await client.request("/notifications/devices", method: "POST", body: body)
        return dto.deliveryAvailable
    }
    func unregisterPushDevice(token: String) async throws { let body = PushDeviceRequestDTO(token: token, environment: Self.pushEnvironment, locale: Locale.current.identifier, timezone: TimeZone.current.identifier); let _: EmptyResponseDTO = try await client.request("/notifications/devices/unregister", method: "POST", body: body) }
    func deleteAccount(confirmation: String) async throws { let _: EmptyResponseDTO = try await client.request("/me", method: "DELETE", body: ["confirmation": confirmation]) }
}
