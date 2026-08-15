package ai.puregamma.android.data.repository

import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.data.remote.dto.*
import ai.puregamma.android.model.*
import org.json.JSONObject

/**
 * 移动端契约 v1 的仓储层（docs/mobile/MOBILE_API_CONTRACT.md）。
 * 后端未实现时（404/501）一律返回不可用/空状态，绝不使用假数据。
 * 当前 Android 产品面仍由 WebView 路由承载，本层用于：
 *  1) 能力发现与入口门控（服务端为准）；
 *  2) 后端接口就绪后的原生接入（DTO/状态机已按契约对齐）。
 */
class MobileRepository(private val api: PureGammaApi) {

    /** 拉取服务端能力。404/501 视为契约缺失 → 全部不可用。 */
    suspend fun getCapabilities(): MobileCapabilities {
        return try {
            val dto = api.getMobileCapabilities()
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

    suspend fun getResearchRuns(): List<ResearchRun> {
        val envelope = api.getResearchRuns()
        return envelope.runs.map { dtoToRun(it) }
    }

    suspend fun createResearchRun(name: String, prompt: String, dataSources: List<String>): ResearchRun {
        val envelope = api.createResearchRun(ResearchRunCreateRequest(name = name, prompt = prompt, dataSources = dataSources))
        return dtoToRun(envelope.run)
    }

    suspend fun getResearchRun(id: String): ResearchRun = dtoToRun(api.getResearchRun(id).run)

    suspend fun cancelResearchRun(id: String): ResearchRun = dtoToRun(api.cancelResearchRun(id).run)

    suspend fun retryResearchRun(id: String): ResearchRun = dtoToRun(api.retryResearchRun(id).run)

    suspend fun getResearchRunEvidence(id: String): List<ResearchEvidence> {
        val envelope = api.getResearchRunEvidence(id)
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

    suspend fun getMemorySettings(): MemorySettings = api.getMemorySettings().settings.toDomain()

    suspend fun updateMemorySettings(
        shortTerm: Boolean?,
        midTerm: Boolean?,
        conversationSummary: Boolean?,
        researchMemory: Boolean?,
        portfolioMemory: Boolean?,
        consentGranted: Boolean,
    ): MemorySettings = api.updateMemorySettings(
        MemorySettingsPatchRequest(
            shortTermEnabled = shortTerm,
            midTermEnabled = midTerm,
            conversationSummaryEnabled = conversationSummary,
            researchMemoryEnabled = researchMemory,
            portfolioMemoryEnabled = portfolioMemory,
            consentGranted = consentGranted,
        ),
    ).settings.toDomain()

    suspend fun getTradingMandates(): List<TradingMandate> =
        api.getTradingMandates().mandates.map { dtoToMandate(it) }

    suspend fun getTradingMandate(id: String): TradingMandate = dtoToMandate(api.getTradingMandate(id).mandate)

    suspend fun pauseMandate(id: String): TradingMandate = dtoToMandate(api.pauseTradingMandate(id).mandate)

    suspend fun resumeMandate(id: String): TradingMandate = dtoToMandate(api.resumeTradingMandate(id).mandate)

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
