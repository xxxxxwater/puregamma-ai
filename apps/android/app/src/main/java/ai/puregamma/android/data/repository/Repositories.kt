package ai.puregamma.android.data.repository

import ai.puregamma.android.agent.AgentPermissionMode
import ai.puregamma.android.agent.AgentRunEventsPage
import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.data.remote.dto.*
import ai.puregamma.android.model.*

class TodayRepository(private val api: PureGammaApi) {

    suspend fun getMarketSnapshot(): List<MarketAsset> {
        val dto = api.getMarketSnapshot()
        return dto.assets?.map { it.toDomain() } ?: emptyList()
    }

    suspend fun getReports(): List<Report> {
        val dto = api.getReports()
        return dto.reports?.map { it.toDomain() } ?: emptyList()
    }

    suspend fun getBillingSummary(): BillingSummary {
        val dto = api.getSubscription()
        return BillingSummary(
            plan = dto.plan ?: "free",
            membershipTier = dto.membershipTier,
            status = dto.subscriptionStatus ?: "unknown",
            credits = dto.creditBalance ?: 0,
        )
    }
}

/** Retrofit's HttpException carries the error body once; keep its envelope as a RetrofitApiException. */
internal suspend fun <T> apiCall(block: suspend () -> T): T = try {
    block()
} catch (error: retrofit2.HttpException) {
    val body = runCatching { error.response()?.errorBody()?.string() }.getOrNull().orEmpty()
    throw RetrofitApiException.fromBody(error.code(), body)
}

class AgentRepository(private val api: PureGammaApi) {

    suspend fun getConversations(): List<AgentConversation> = apiCall {
        api.getConversations().conversations?.map { it.toDomain() } ?: emptyList()
    }

    suspend fun createConversation(title: String? = null): AgentConversation = apiCall {
        api.createConversation(mapOf("title" to title)).conversation.toDomain()
    }

    suspend fun getConversation(id: String): Pair<AgentConversation, List<AgentMessage>> {
        val snapshot = getSnapshot(id)
        return snapshot.conversation to snapshot.messages
    }

    /** The server's record of a conversation, including the run it is still producing. */
    suspend fun getSnapshot(id: String): AgentConversationSnapshot = apiCall {
        val dto = api.getConversation(id)
        AgentConversationSnapshot(dto.conversation.toDomain(), dto.messages?.map { it.toDomain() } ?: emptyList(), dto.activeRunId)
    }

    suspend fun updateConversation(id: String, title: String?, archived: Boolean?): AgentConversation = apiCall {
        api.updateConversation(id, ConversationPatchRequest(title, archived)).conversation.toDomain()
    }

    suspend fun setPermission(id: String, mode: AgentPermissionMode): AgentConversation = apiCall {
        api.updateConversationPermission(id, mapOf("permission_mode" to mode.wire)).conversation.toDomain()
    }

    suspend fun deleteConversation(id: String) {
        safeCall { api.deleteConversation(id) }
    }

    suspend fun getCapabilities(): AgentCapabilities = apiCall {
        val dto = api.getCapabilities()
        AgentCapabilities(
            plan = dto.capabilities.plan,
            dataSources = dto.capabilities.allowedDataSources,
            dailyRuns = dto.capabilities.agentDailyRuns,
            concurrentRuns = dto.capabilities.agentConcurrentRuns,
            credits = dto.quota.creditBalance,
            remaining = dto.quota.remaining,
            models = dto.models?.map { model ->
                AgentModel(
                    id = model.id,
                    name = model.displayName,
                    provider = model.provider,
                    available = model.available,
                    reason = model.reason,
                    category = model.category ?: "generation",
                )
            } ?: emptyList(),
        )
    }

    suspend fun getPermissionModes(): List<AgentPermissionMode> = apiCall {
        AgentPermissionMode.selectable(api.getWorkspaceCapabilities().permissionModes.orEmpty())
    }

    suspend fun getRunEvents(runId: String, after: Int): AgentRunEventsPage = apiCall {
        AgentRunEventsPage.parse(api.getRunEvents(runId, after))
    }

    suspend fun cancelRun(runId: String) {
        safeCall { api.cancelRun(runId) }
    }

    fun buildAgentMessageRequest(
        content: String,
        locale: String,
        dataSources: List<String>,
        skills: List<String>,
        customPrompt: String,
        model: String,
        clientRequestId: String? = null,
    ): AgentMessageRequest {
        return AgentMessageRequest(
            content = content,
            locale = locale,
            dataSources = dataSources,
            skills = skills,
            customPrompt = customPrompt,
            attachments = emptyList(),
            model = model,
            clientRequestId = clientRequestId,
        )
    }

    private suspend fun safeCall(block: suspend () -> retrofit2.Response<Void>) {
        val response = block()
        if (!response.isSuccessful) {
            val body = runCatching { response.errorBody()?.string() }.getOrNull().orEmpty()
            throw RetrofitApiException.fromBody(response.code(), body)
        }
    }
}

/** Server-computed LIVE NAV (§8.3). No account is a state, never a zero NAV. */
class LiveNavRepository(private val api: PureGammaApi) {
    suspend fun current(): LiveNavState = try {
        val dto = apiCall { api.getLiveNav() }
        LiveNavState.Loaded(dto.nav.toDomain(dto.dailyPnl, dto.dailyReturn))
    } catch (error: RetrofitApiException) {
        if (isNoAccount(error)) LiveNavState.NoAccount else throw error
    }

    suspend fun history(limit: Int = 100): List<LiveNav> = apiCall {
        api.getLiveNavHistory(limit).history.orEmpty().map { it.toDomain(null, null) }
    }

    companion object {
        fun isNoAccount(error: RetrofitApiException): Boolean =
            error.status == 404 && (error.detail?.code ?: error.code) == "TRADING_ACCOUNT_NOT_FOUND"
    }
}

internal fun LiveNavDto.toDomain(dailyPnl: String?, dailyReturn: String?) = LiveNav(
    accountId = accountId.orEmpty(),
    currency = currency ?: "USD",
    nav = decimalOrNull(nav),
    cash = decimalOrNull(cash),
    grossExposure = decimalOrNull(grossExposure),
    netExposure = decimalOrNull(netExposure),
    realizedPnl = decimalOrNull(realizedPnl),
    unrealizedPnl = decimalOrNull(unrealizedPnl),
    dailyPnl = decimalOrNull(dailyPnl),
    dailyReturn = decimalOrNull(dailyReturn),
    calculatedAt = calculatedAt?.let { parseInstantOrNull(it) },
    isStale = isStale ?: false,
)

class ResearchRepository(private val api: PureGammaApi) {

    suspend fun getReports(): List<Report> {
        val dto = api.getReports()
        return dto.reports?.map { it.toDomain() } ?: emptyList()
    }

    suspend fun getLongGamma(currency: String): Triple<List<OptionCandidate>, String?, String?> {
        val dto = api.getLongGamma(currency)
        val candidates = dto.candidates?.map { it.toDomain() } ?: emptyList()
        return Triple(candidates, dto.status, dto.error)
    }
}

class PortfolioRepository(private val api: PureGammaApi) {

    suspend fun getPortfolio(): Portfolio {
        val dto = api.getPortfolio()
        return dto.toDomain()
    }

    suspend fun getAutopilot(): Autopilot {
        val dto = api.getAutopilot()
        return dto.toDomain()
    }

    suspend fun runAutopilotReview(): Autopilot {
        val dto = api.runAutopilotReview()
        return dto.toDomain()
    }

    suspend fun connectHyperliquid(address: String): Portfolio {
        val dto = api.connectHyperliquid(mapOf("address" to address))
        return dto.toDomain()
    }

    suspend fun syncConnection(id: String): Portfolio {
        val dto = api.syncConnection(id)
        return dto.toDomain()
    }

    suspend fun deleteConnection(id: String) {
        safeCall { api.deleteConnection(id) }
    }

    suspend fun createPlaidLinkToken(): String {
        val dto = api.createPlaidLinkToken(emptyMap())
        return dto.linkToken
    }

    suspend fun exchangePlaidToken(publicToken: String): Portfolio {
        val dto = api.exchangePlaidToken(mapOf("public_token" to publicToken))
        return dto.toDomain()
    }

    suspend fun ibkrOAuthStart(redirectUri: String): String {
        val dto = api.ibkrOAuthStart(IbkrOAuthStartRequest(redirectUri))
        return dto.authorizeUrl
    }

    suspend fun ibkrOAuthComplete(code: String): Portfolio {
        val dto = api.ibkrOAuthComplete(IbkrOAuthCompleteRequest(code))
        return dto.toDomain()
    }

    private suspend fun safeCall(block: suspend () -> retrofit2.Response<Void>) {
        val response = block()
        if (!response.isSuccessful) {
            throw RetrofitApiException(response.code(), "Request failed (${response.code()})")
        }
    }
}

class AccountRepository(private val api: PureGammaApi) {

    suspend fun deleteAccount() {
        val response = api.deleteAccount()
        if (!response.isSuccessful) {
            throw RetrofitApiException(response.code(), "Account deletion failed")
        }
    }

    suspend fun registerPushDevice(token: String, locale: String, timezone: String): Boolean {
        val body = PushDeviceRequestDto(token = token, environment = "android", locale = locale, timezone = timezone)
        val dto = api.registerPushDevice(body)
        return dto.deliveryAvailable
    }

    suspend fun unregisterPushDevice(token: String) {
        safeCall { api.unregisterPushDevice(mapOf("token" to token)) }
    }

    private suspend fun safeCall(block: suspend () -> retrofit2.Response<Void>) {
        val response = block()
        if (!response.isSuccessful) {
            throw RetrofitApiException(response.code(), "Request failed (${response.code()})")
        }
    }
}

private fun MarketAssetDto.toDomain() = MarketAsset(
    symbol = symbol,
    price = price ?: 0.0,
    volume24h = volume24h ?: 0.0,
    change24h = change24h,
    fundingRate = fundingRate,
    openInterest = openInterest,
    riskScore = riskScore,
    timestamp = timestamp?.let { parseInstant(it) },
    source = sourceDisplay ?: source ?: "-",
    realtime = isRealtime ?: false,
)

private fun ReportDto.toDomain() = Report(
    id = id,
    title = title,
    type = reportType,
    markdown = contentMarkdown,
    assets = assets ?: emptyList(),
    createdAt = createdAt?.let { parseInstant(it) },
)

private fun ConversationDto.toDomain() = AgentConversation(
    id = id,
    title = title,
    status = status,
    summary = summary,
    updatedAt = updatedAt?.let { parseInstant(it) },
    permissionMode = permissionMode,
)

private fun MessageDto.toDomain() = AgentMessage(
    id = id,
    conversationId = conversationId,
    role = role,
    content = content ?: "",
    status = status ?: "ready",
    sources = sources?.map { source ->
        AgentSource(
            index = source.citationIndex,
            provider = source.provider,
            title = source.title,
            url = source.url,
        )
    } ?: emptyList(),
    error = errorMessage,
)

private fun PortfolioDto.toDomain() = Portfolio(
    connected = connected ?: false,
    stale = stale ?: false,
    asOf = dataAsOf?.let { parseInstant(it) },
    nav = decimalOrNull(nav),
    availableCash = decimalOrNull(availableCash),
    connections = connections?.map { conn ->
        PortfolioConnection(
            id = conn.id,
            provider = conn.provider,
            name = conn.name,
            status = conn.status,
            lastSync = conn.lastSync?.let { parseInstant(it) },
            error = conn.error,
        )
    } ?: emptyList(),
    navHistory = navHistory?.mapNotNull { point ->
        decimalOrNull(point.nav)?.let { NavPoint(date = parseInstant(point.date), value = it) }
    } ?: emptyList(),
)

private fun AutopilotDto.toDomain() = Autopilot(
    enabled = config.enabled,
    cadence = config.cadence,
    autoSync = config.autoSync,
    riskAlerts = config.riskAlerts,
    longGammaWatch = config.longGammaWatch,
    delivery = config.delivery,
    accountCount = accountCount,
    findings = findings?.map { AutopilotFinding(it.severity, it.title) } ?: emptyList(),
    lastReview = lastReview?.let { parseInstant(it) },
)

private fun OptionCandidateDto.toDomain() = OptionCandidate(
    instrument = instrument,
    underlying = underlying,
    type = optionType,
    strike = strike,
    markIv = markIv,
    gamma = greeks?.gamma,
    theta = greeks?.theta,
    score = researchScore,
    expiry = expiry?.let { parseInstant(it) },
    timestamp = timestamp?.let { parseInstant(it) },
    rationale = rationale ?: emptyList(),
)

private fun parseInstant(raw: String): java.time.Instant = parseInstantOrNull(raw) ?: java.time.Instant.EPOCH
