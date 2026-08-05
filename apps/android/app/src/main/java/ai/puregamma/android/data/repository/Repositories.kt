package ai.puregamma.android.data.repository

import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.data.remote.dto.*
import ai.puregamma.android.model.*

class TodayRepository(var api: PureGammaApi) {

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
            status = dto.subscriptionStatus ?: "unknown",
            credits = dto.creditBalance ?: 0,
        )
    }
}

class AgentRepository(var api: PureGammaApi) {

    suspend fun getConversations(): List<AgentConversation> {
        val dto = api.getConversations()
        return dto.conversations?.map { it.toDomain() } ?: emptyList()
    }

    suspend fun createConversation(title: String? = null): AgentConversation {
        val body = mapOf("title" to title)
        val dto = api.createConversation(body)
        return dto.conversation.toDomain()
    }

    suspend fun getConversation(id: String): Pair<AgentConversation, List<AgentMessage>> {
        val dto = api.getConversation(id)
        val conv = dto.conversation.toDomain()
        val msgs = dto.messages?.map { it.toDomain() } ?: emptyList()
        return conv to msgs
    }

    suspend fun updateConversation(id: String, title: String?, archived: Boolean?): AgentConversation {
        val body = ConversationPatchRequest(title, archived)
        val dto = api.updateConversation(id, body)
        return dto.conversation.toDomain()
    }

    suspend fun deleteConversation(id: String) {
        safeCall { api.deleteConversation(id) }
    }

    suspend fun getCapabilities(): AgentCapabilities {
        val dto = api.getCapabilities()
        return AgentCapabilities(
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
                )
            } ?: emptyList(),
        )
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
    ): AgentMessageRequest {
        return AgentMessageRequest(
            content = content,
            locale = locale,
            dataSources = dataSources,
            skills = skills,
            customPrompt = customPrompt,
            attachments = emptyList(),
            model = model,
        )
    }

    private suspend fun safeCall(block: suspend () -> retrofit2.Response<Void>) {
        val response = block()
        if (!response.isSuccessful) {
            throw RetrofitApiException(response.code(), "Request failed (${response.code()})")
        }
    }
}

class ResearchRepository(var api: PureGammaApi) {

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

class PortfolioRepository(var api: PureGammaApi) {

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

class AccountRepository(var api: PureGammaApi) {

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
    nav = nav,
    availableCash = availableCash,
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
    navHistory = navHistory?.map { point ->
        NavPoint(date = parseInstant(point.date), value = point.nav)
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

private fun parseInstant(raw: String): java.time.Instant {
    return runCatching { java.time.Instant.parse(raw) }.getOrNull() ?: java.time.Instant.EPOCH
}
