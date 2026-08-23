package ai.puregamma.android.data.repository

import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.data.remote.dto.*
import ai.puregamma.android.model.*
import org.json.JSONObject

/**
 * Repository 层门控错误：capabilities 缺失/为 false、非法输入或 LIVE 操作一律在此层拦截，
 * 不发起网络请求。UI 门控只是展示层保护，这里才是客户端硬边界；服务端仍做最终校验。
 */
class MobileFeatureException(val kind: Kind, override val message: String) : Exception(message) {
    enum class Kind { CONTRACT_MISSING, DISABLED, INVALID_INPUT, LIVE_DISABLED }
}

/**
 * 移动端契约 v1 的仓储层（docs/mobile/MOBILE_API_CONTRACT.md）。
 * 后端未实现时（404/501）一律返回不可用/空状态，绝不使用假数据。
 * 当前 Android 产品面仍由 WebView 路由承载，本层用于：
 *  1) 能力发现与入口门控（服务端为准）；
 *  2) 后端接口就绪后的原生接入（DTO/状态机已按契约对齐）。
 */
class MobileRepository(
    private val api: PureGammaApi,
    private val capabilitiesProvider: () -> MobileCapabilities,
) {

    private val capabilities: MobileCapabilities get() = capabilitiesProvider()

    /**
     * Normalize every API failure into [RetrofitApiException] regardless of
     * whether the production OkHttpClient has [ApiErrorInterceptor] wired in:
     * without it, Retrofit's suspend `await()` throws a bare
     * `retrofit2.HttpException` for non-2xx responses, and callers must not
     * depend on interceptor wiring to branch on status.
     */
    private suspend fun <T> apiCall(block: suspend () -> T): T {
        try {
            return block()
        } catch (e: retrofit2.HttpException) {
            throw RetrofitApiException(e.code(), e.message())
        }
    }

    private companion object {
        val ID_PATTERN = Regex("^[A-Za-z0-9_-]{1,64}$")
        val ALLOWED_DATA_SOURCES = setOf("market", "news", "research")
        const val NAME_MAX_LENGTH = 100
        const val PROMPT_MAX_LENGTH = 4000
        const val DATA_SOURCE_MAX_COUNT = 8
        const val DATA_SOURCE_MAX_LENGTH = 32
    }

    /** 拉取服务端能力。404/501 视为契约缺失 → 全部不可用。 */
    suspend fun getCapabilities(): MobileCapabilities {
        return try {
            val dto = apiCall { api.getMobileCapabilities() }
            MobileCapabilities(
                harnessResearchEnabled = dto.harnessResearchEnabled ?: false,
                memoryServiceEnabled = dto.memoryServiceEnabled ?: false,
                autoTradingEnabled = dto.autoTradingEnabled ?: false,
                paperTradingEnabled = dto.paperTradingEnabled ?: false,
                shadowTradingEnabled = dto.shadowTradingEnabled ?: false,
                liveTradingEnabled = dto.liveTradingEnabled ?: false,
                userCanStartResearch = dto.userCanStartResearch ?: false,
                userCanManageMemory = dto.userCanManageMemory ?: false,
                userCanViewTradingMandates = dto.userCanViewTradingMandates ?: false,
                userCanPauseMandates = dto.userCanPauseMandates ?: false,
                harnessRetryEnabled = dto.harnessRetryEnabled ?: false,
                appMinVersion = dto.appMinVersion,
                maintenanceMessage = dto.maintenanceMessage,
                serverContractAvailable = true,
            )
        } catch (e: RetrofitApiException) {
            if (e.status == 404 || e.status == 501) MobileCapabilities.UNAVAILABLE else throw e
        }
    }

    // ---- 门控原语 ----

    private fun requireContract() {
        if (!capabilities.serverContractAvailable) {
            throw MobileFeatureException(MobileFeatureException.Kind.CONTRACT_MISSING, "Feature not available yet")
        }
    }

    private fun requireHarnessResearch() {
        requireContract()
        if (!capabilities.harnessResearchEnabled) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "Harness research is disabled for your account")
        }
    }

    private fun requireMemory(mutation: Boolean) {
        requireContract()
        if (!capabilities.memoryServiceEnabled || (mutation && !capabilities.userCanManageMemory)) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "Memory service is disabled for your account")
        }
    }

    private fun requireMandatesView() {
        requireContract()
        if (!capabilities.autoTradingEnabled || !capabilities.userCanViewTradingMandates) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "Auto-trading mandates are disabled for your account")
        }
    }

    /** ID 校验：禁止把任意用户输入直接拼进 URL 路径。 */
    private fun requireId(raw: String, label: String): String {
        val trimmed = raw.trim()
        if (trimmed.isEmpty() || trimmed.length > 64 || !ID_PATTERN.matches(trimmed)) {
            throw MobileFeatureException(MobileFeatureException.Kind.INVALID_INPUT, "Invalid $label")
        }
        return trimmed
    }

    // ---- Harness 研究任务 ----

    suspend fun getResearchRuns(): List<ResearchRun> {
        requireHarnessResearch()
        val envelope = apiCall { api.getResearchRuns() }
        return envelope.runs.map { dtoToRun(it) }
    }

    suspend fun createResearchRun(name: String, prompt: String, dataSources: List<String>): ResearchRun {
        requireHarnessResearch()
        if (!capabilities.userCanStartResearch) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "Harness research is disabled for your account")
        }
        val taskName = name.trim().takeIf { it.isNotEmpty() && it.length <= NAME_MAX_LENGTH }
            ?: throw MobileFeatureException(MobileFeatureException.Kind.INVALID_INPUT, "Invalid task name")
        val taskPrompt = prompt.trim().takeIf { it.isNotEmpty() && it.length <= PROMPT_MAX_LENGTH }
            ?: throw MobileFeatureException(MobileFeatureException.Kind.INVALID_INPUT, "Invalid research prompt")
        val sources = dataSources.map { it.trim().lowercase() }
            .filter { it.isNotEmpty() && it.length <= DATA_SOURCE_MAX_LENGTH && ALLOWED_DATA_SOURCES.contains(it) }
            .distinct()
            .take(DATA_SOURCE_MAX_COUNT)
        val envelope = apiCall { api.createResearchRun(ResearchRunCreateRequest(name = taskName, prompt = taskPrompt, dataSources = sources)) }
        return dtoToRun(envelope.run)
    }

    suspend fun getResearchRun(id: String): ResearchRun {
        requireHarnessResearch()
        return dtoToRun(apiCall { api.getResearchRun(requireId(id, "run identifier")).run })
    }

    suspend fun cancelResearchRun(id: String): ResearchRun {
        requireHarnessResearch()
        return dtoToRun(apiCall { api.cancelResearchRun(requireId(id, "run identifier")).run })
    }

    suspend fun retryResearchRun(id: String): ResearchRun {
        requireHarnessResearch()
        if (!capabilities.harnessRetryEnabled) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "Retry is disabled for this run")
        }
        return dtoToRun(apiCall { api.retryResearchRun(requireId(id, "run identifier")).run })
    }

    suspend fun getResearchRunEvidence(id: String): List<ResearchEvidence> {
        requireHarnessResearch()
        val envelope = apiCall { api.getResearchRunEvidence(requireId(id, "run identifier")) }
        return envelope.evidence.map {
            ResearchEvidence(
                id = it.id,
                runId = it.runId,
                citationIndex = it.citationIndex ?: 0,
                provider = it.provider,
                title = it.title,
                url = it.url,
                verified = it.isVerified ?: false,
                verificationNote = it.verificationNote,
            )
        }
    }

    // ---- Memory ----

    suspend fun getMemorySettings(): MemorySettings {
        requireMemory(mutation = false)
        return apiCall { api.getMemorySettings() }.settings.toDomain()
    }

    suspend fun updateMemorySettings(
        shortTerm: Boolean?,
        midTerm: Boolean?,
        conversationSummary: Boolean?,
        researchMemory: Boolean?,
        portfolioMemory: Boolean?,
        consentGranted: Boolean,
    ): MemorySettings {
        requireMemory(mutation = true)
        return apiCall {
            api.updateMemorySettings(
                MemorySettingsPatchRequest(
                    shortTermEnabled = shortTerm,
                    midTermEnabled = midTerm,
                    conversationSummaryEnabled = conversationSummary,
                    researchMemoryEnabled = researchMemory,
                    portfolioMemoryEnabled = portfolioMemory,
                    consentGranted = consentGranted,
                ),
            )
        }.settings.toDomain()
    }

    // ---- 自动交易 Mandate（只读 + 有限管理） ----

    suspend fun getTradingMandates(): List<TradingMandate> {
        requireMandatesView()
        return apiCall { api.getTradingMandates() }.mandates.map { dtoToMandate(it) }
    }

    suspend fun getTradingMandate(id: String): TradingMandate {
        requireMandatesView()
        return dtoToMandate(apiCall { api.getTradingMandate(requireId(id, "mandate identifier")).mandate })
    }

    /**
     * 暂停：先查环境，仅 PAPER/SHADOW 且能力允许才调用；已暂停则幂等返回，不重复请求。
     * LIVE（含未知环境降级）一律在 Repository 层拦截，不发网络请求。
     */
    suspend fun pauseMandate(id: String): TradingMandate {
        requireMandatesView()
        val mandateId = requireId(id, "mandate identifier")
        val current = getTradingMandate(mandateId)
        if (current.environment.isLive) {
            throw MobileFeatureException(MobileFeatureException.Kind.LIVE_DISABLED, "LIVE is disabled and cannot be started from this app")
        }
        if (current.paused) return current // 幂等
        if (!MandateActionPolicy.pauseAllowed(current.environment, current.paused, capabilities)) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "This mandate cannot be paused from mobile")
        }
        return dtoToMandate(apiCall { api.pauseTradingMandate(mandateId).mandate })
    }

    /** 恢复：同样的硬边界与幂等语义；服务端仍会二次校验。 */
    suspend fun resumeMandate(id: String): TradingMandate {
        requireMandatesView()
        val mandateId = requireId(id, "mandate identifier")
        val current = getTradingMandate(mandateId)
        if (current.environment.isLive) {
            throw MobileFeatureException(MobileFeatureException.Kind.LIVE_DISABLED, "LIVE is disabled and cannot be started from this app")
        }
        if (!current.paused) return current // 幂等
        if (!MandateActionPolicy.resumeAllowed(current.environment, current.paused, capabilities)) {
            throw MobileFeatureException(MobileFeatureException.Kind.DISABLED, "This mandate cannot be resumed from mobile")
        }
        return dtoToMandate(apiCall { api.resumeTradingMandate(mandateId).mandate })
    }

    private fun dtoToRun(dto: ResearchRunDto) = ResearchRun(
        id = dto.id,
        name = dto.name,
        state = ResearchRunState.fromServer(dto.status),
        verification = when (dto.verification?.uppercase()) {
            "VERIFIED" -> ResearchVerification.VERIFIED
            "PARTIAL" -> ResearchVerification.PARTIAL
            "DEGRADED" -> ResearchVerification.DEGRADED
            "FAILED" -> ResearchVerification.FAILED
            else -> ResearchVerification.INCOMPLETE
        },
        createdAt = dto.createdAt?.let { parseInstantOrNull(it) },
        updatedAt = dto.updatedAt?.let { parseInstantOrNull(it) },
        creditsUsed = dto.creditsUsed,
        creditsEstimate = dto.creditsEstimate,
        dataSources = dto.dataSources ?: emptyList(),
        evidenceCount = dto.evidenceCount ?: 0,
        citationCount = dto.citationCount ?: 0,
        degraded = dto.isDegraded ?: false,
        errorMessage = dto.errorMessage,
        summary = dto.summary,
    )

    private fun dtoToMandate(dto: TradingMandateDto) = TradingMandate(
        id = dto.id,
        name = dto.name,
        strategyName = dto.strategyName ?: "-",
        environment = TradingEnvironment.fromServer(dto.environment),
        paused = dto.paused ?: true,
        updatedAt = dto.updatedAt?.let { parseInstantOrNull(it) },
        lastRunAt = dto.lastRunAt?.let { parseInstantOrNull(it) },
        lastRunStatus = dto.lastRunStatus,
        riskBlockReason = dto.riskBlockReason,
    )

    private fun MemorySettingsDto.toDomain() = MemorySettings(
        shortTermEnabled = shortTermEnabled,
        midTermEnabled = midTermEnabled,
        conversationSummaryEnabled = conversationSummaryEnabled,
        researchMemoryEnabled = researchMemoryEnabled,
        portfolioMemoryEnabled = portfolioMemoryEnabled,
        consentRequired = consentRequired ?: true,
        retentionDays = retentionDays ?: 30,
    )
}

internal fun parseInstantOrNull(raw: String): java.time.Instant? =
    runCatching { java.time.Instant.parse(raw) }.getOrNull()

