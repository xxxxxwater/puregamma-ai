package ai.puregamma.android.model

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

/**
 * 服务端能力发现结果。所有新功能入口以此为准；缺失字段一律视为 false。
 * 该结论只用于 UI 展示与入口门控，绝不用于本地判定额度/权限/交易资格。
 */
data class MobileCapabilities(
    val harnessResearchEnabled: Boolean = false,
    val memoryServiceEnabled: Boolean = false,
    val autoTradingEnabled: Boolean = false,
    val paperTradingEnabled: Boolean = false,
    val shadowTradingEnabled: Boolean = false,
    /** 仅作信息展示。无论该值为何，移动端都不提供 LIVE 入口。 */
    val liveTradingEnabled: Boolean = false,
    val userCanStartResearch: Boolean = false,
    val userCanManageMemory: Boolean = false,
    val userCanViewTradingMandates: Boolean = false,
    val userCanPauseMandates: Boolean = false,
    val harnessRetryEnabled: Boolean = false,
    val appMinVersion: String? = null,
    val maintenanceMessage: String? = null,
    /** false 表示后端尚未提供 /api/mobile/capabilities，全部新功能按不可用处理。 */
    val serverContractAvailable: Boolean = false,
) {
    companion object {
        val UNAVAILABLE = MobileCapabilities()
    }
}

/** 服务端研究任务状态；idle/submitting 仅存在于客户端提交阶段。 */
enum class ResearchRunState {
    IDLE, SUBMITTING,
    QUEUED, PREPARING, RUNNING, VALIDATING,
    COMPLETED, DEGRADED, FAILED, CANCELED, TIMED_OUT;

    val isTerminal: Boolean
        get() = this == COMPLETED || this == DEGRADED || this == FAILED || this == CANCELED || this == TIMED_OUT

    val isActive: Boolean
        get() = this == QUEUED || this == PREPARING || this == RUNNING || this == VALIDATING

    val isRetryable: Boolean
        get() = this == FAILED || this == CANCELED || this == TIMED_OUT

    companion object {
        fun fromServer(raw: String?): ResearchRunState =
            entries.firstOrNull { it.name.equals(raw?.uppercase(), ignoreCase = true) && it != IDLE && it != SUBMITTING }
                ?: IDLE
    }
}

enum class ResearchVerification { VERIFIED, PARTIAL, DEGRADED, FAILED, INCOMPLETE }

data class ResearchRun(
    val id: String,
    val name: String,
    val state: ResearchRunState,
    val verification: ResearchVerification,
    val createdAt: Instant?,
    val updatedAt: Instant?,
    val creditsUsed: Double?,
    val creditsEstimate: Double?,
    val dataSources: List<String>,
    val evidenceCount: Int,
    val citationCount: Int,
    val degraded: Boolean,
    val errorMessage: String?,
    val summary: String?,
)

data class ResearchEvidence(
    val id: String,
    val runId: String,
    val citationIndex: Int,
    val provider: String,
    val title: String,
    val url: String?,
    val verified: Boolean,
    val verificationNote: String?,
)

/** 交易环境。LIVE 永远不可操作（客户端硬约束）。 */
enum class TradingEnvironment {
    OFF, PAPER, SHADOW, LIVE_DISABLED, UNAVAILABLE;

    val isLive: Boolean get() = this == LIVE_DISABLED
    val canBePausedOrResumed: Boolean get() = this == PAPER || this == SHADOW

    companion object {
        fun fromServer(raw: String?): TradingEnvironment =
            entries.firstOrNull { it.name.equals(raw?.uppercase(), ignoreCase = true) } ?: UNAVAILABLE
    }
}

data class TradingMandate(
    val id: String,
    val name: String,
    val strategyName: String,
    val environment: TradingEnvironment,
    val paused: Boolean,
    val updatedAt: Instant?,
    val lastRunAt: Instant?,
    val lastRunStatus: String?,
    val riskBlockReason: String?,
)

data class MandateRiskLimits(
    val maxNotional: Double?,
    val dailyLossLimit: Double?,
    val maxLeverage: Double?,
    val maxPositionSizePct: Double?,
)

/**
 * 移动端允许的动作策略。所有动作仍由服务端二次校验；该策略只决定 UI 是否渲染按钮。
 */
object MandateActionPolicy {
    fun pauseAllowed(environment: TradingEnvironment, paused: Boolean, capabilities: MobileCapabilities): Boolean =
        environment.canBePausedOrResumed && !paused && capabilities.userCanPauseMandates && capabilities.autoTradingEnabled

    fun resumeAllowed(environment: TradingEnvironment, paused: Boolean, capabilities: MobileCapabilities): Boolean =
        environment.canBePausedOrResumed && paused && capabilities.userCanPauseMandates && capabilities.autoTradingEnabled

    /** LIVE 永远不可操作：即使 capability、部署标记或本地配置全部开启。 */
    fun liveActionAllowed(environment: TradingEnvironment): Boolean = false
}

enum class MemoryItemLifecycle { SAVED, PENDING, REJECTED, EXPIRED, DELETED }

data class MemorySettings(
    val shortTermEnabled: Boolean = false,
    val midTermEnabled: Boolean = false,
    val conversationSummaryEnabled: Boolean = false,
    val researchMemoryEnabled: Boolean = false,
    val portfolioMemoryEnabled: Boolean = false,
    val consentRequired: Boolean = true,
    val retentionDays: Int = 30,
)

data class MemoryItem(
    val id: String,
    val scope: String,
    val kind: String,
    val contentPreview: String,
    val lifecycle: MemoryItemLifecycle,
    val createdAt: Instant?,
)

data class MemoryProposal(
    val id: String,
    val scope: String,
    val contentPreview: String,
    val source: String,
    val status: String,
)

// ---- 解析辅助（与 Models.kt 既有风格一致，容忍未知/缺失字段） ----

internal fun JSONObject.toMobileCapabilities(): MobileCapabilities {
    val flag = { key: String -> if (has(key) && !isNull(key)) optBoolean(key) else false }
    return MobileCapabilities(
        harnessResearchEnabled = flag("harness_research_enabled"),
        memoryServiceEnabled = flag("memory_service_enabled"),
        autoTradingEnabled = flag("auto_trading_enabled"),
        paperTradingEnabled = flag("paper_trading_enabled"),
        shadowTradingEnabled = flag("shadow_trading_enabled"),
        liveTradingEnabled = flag("live_trading_enabled"),
        userCanStartResearch = flag("user_can_start_research"),
        userCanManageMemory = flag("user_can_manage_memory"),
        userCanViewTradingMandates = flag("user_can_view_trading_mandates"),
        userCanPauseMandates = flag("user_can_pause_mandates"),
        harnessRetryEnabled = flag("harness_retry_enabled"),
        appMinVersion = nullableString("app_min_version"),
        maintenanceMessage = nullableString("maintenance_message"),
        serverContractAvailable = true,
    )
}

internal fun JSONObject.toResearchRun(): ResearchRun = ResearchRun(
    id = string("id"),
    name = string("name"),
    state = ResearchRunState.fromServer(nullableString("status")),
    verification = when (nullableString("verification")?.uppercase()) {
        "VERIFIED" -> ResearchVerification.VERIFIED
        "PARTIAL" -> ResearchVerification.PARTIAL
        "DEGRADED" -> ResearchVerification.DEGRADED
        "FAILED" -> ResearchVerification.FAILED
        else -> ResearchVerification.INCOMPLETE
    },
    createdAt = instant("created_at"),
    updatedAt = instant("updated_at"),
    creditsUsed = nullableDouble("credits_used"),
    creditsEstimate = nullableDouble("credits_estimate"),
    dataSources = optJSONArray("data_sources").strings(),
    evidenceCount = optInt("evidence_count"),
    citationCount = optInt("citation_count"),
    degraded = optBoolean("is_degraded"),
    errorMessage = nullableString("error_message"),
    summary = nullableString("summary"),
)

internal fun JSONObject.toTradingMandate(): TradingMandate = TradingMandate(
    id = string("id"),
    name = string("name"),
    strategyName = nullableString("strategy_name") ?: "-",
    environment = TradingEnvironment.fromServer(nullableString("environment")),
    paused = if (has("paused") && !isNull("paused")) optBoolean("paused") else true,
    updatedAt = instant("updated_at"),
    lastRunAt = instant("last_run_at"),
    lastRunStatus = nullableString("last_run_status"),
    riskBlockReason = nullableString("risk_block_reason"),
)

internal fun JSONObject.toMemorySettings(): MemorySettings = MemorySettings(
    shortTermEnabled = optBoolean("short_term_enabled"),
    midTermEnabled = optBoolean("mid_term_enabled"),
    conversationSummaryEnabled = optBoolean("conversation_summary_enabled"),
    researchMemoryEnabled = optBoolean("research_memory_enabled"),
    portfolioMemoryEnabled = optBoolean("portfolio_memory_enabled"),
    consentRequired = if (has("consent_required") && !isNull("consent_required")) optBoolean("consent_required") else true,
    retentionDays = optInt("retention_days", 30),
)

internal fun JSONObject.toMemoryItem(): MemoryItem = MemoryItem(
    id = string("id"),
    scope = string("scope"),
    kind = string("kind"),
    contentPreview = string("content_preview"),
    lifecycle = when (nullableString("status")?.uppercase()) {
        "PENDING" -> MemoryItemLifecycle.PENDING
        "REJECTED" -> MemoryItemLifecycle.REJECTED
        "EXPIRED" -> MemoryItemLifecycle.EXPIRED
        "DELETED" -> MemoryItemLifecycle.DELETED
        else -> MemoryItemLifecycle.SAVED
    },
    createdAt = instant("created_at"),
)

internal fun JSONObject.toMemoryProposal(): MemoryProposal = MemoryProposal(
    id = string("id"),
    scope = string("scope"),
    contentPreview = string("content_preview"),
    source = string("source"),
    status = string("status"),
)

internal fun JSONArray?.jsonObjects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }

internal fun JSONObject.optInt(key: String, default: Int): Int =
    if (!has(key) || isNull(key)) default else optInt(key)
