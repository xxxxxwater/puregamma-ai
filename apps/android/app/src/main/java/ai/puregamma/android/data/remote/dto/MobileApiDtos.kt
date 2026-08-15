package ai.puregamma.android.data.remote.dto

import com.google.gson.annotations.SerializedName

// Capabilities：全部字段可空，后端逐项开放，客户端缺失即视为 false。

data class MobileCapabilitiesDto(
    @SerializedName("harness_research_enabled") val harnessResearchEnabled: Boolean?,
    @SerializedName("memory_service_enabled") val memoryServiceEnabled: Boolean?,
    @SerializedName("auto_trading_enabled") val autoTradingEnabled: Boolean?,
    @SerializedName("paper_trading_enabled") val paperTradingEnabled: Boolean?,
    @SerializedName("shadow_trading_enabled") val shadowTradingEnabled: Boolean?,
    @SerializedName("live_trading_enabled") val liveTradingEnabled: Boolean?,
    @SerializedName("user_can_start_research") val userCanStartResearch: Boolean?,
    @SerializedName("user_can_manage_memory") val userCanManageMemory: Boolean?,
    @SerializedName("user_can_view_trading_mandates") val userCanViewTradingMandates: Boolean?,
    @SerializedName("user_can_pause_mandates") val userCanPauseMandates: Boolean?,
    @SerializedName("harness_retry_enabled") val harnessRetryEnabled: Boolean?,
    @SerializedName("app_min_version") val appMinVersion: String?,
    @SerializedName("maintenance_message") val maintenanceMessage: String?,
)

// Research runs

data class ResearchRunCreateRequest(
    val name: String,
    val prompt: String,
    @SerializedName("data_sources") val dataSources: List<String>,
    val skill: String = "harness_deep_research",
)

data class ResearchRunDto(
    val id: String,
    val name: String,
    val status: String?,
    val verification: String?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("updated_at") val updatedAt: String?,
    @SerializedName("credits_used") val creditsUsed: Double?,
    @SerializedName("credits_estimate") val creditsEstimate: Double?,
    @SerializedName("data_sources") val dataSources: List<String>?,
    @SerializedName("evidence_count") val evidenceCount: Int?,
    @SerializedName("citation_count") val citationCount: Int?,
    @SerializedName("is_degraded") val isDegraded: Boolean?,
    @SerializedName("error_message") val errorMessage: String?,
    val summary: String?,
)

data class ResearchRunEnvelopeDto(val run: ResearchRunDto)
data class ResearchRunsEnvelopeDto(
    val runs: List<ResearchRunDto>,
    val total: Int?,
    val limit: Int?,
    val offset: Int?,
)

data class ResearchEvidenceDto(
    val id: String,
    @SerializedName("run_id") val runId: String,
    @SerializedName("citation_index") val citationIndex: Int?,
    val provider: String,
    val title: String,
    val url: String?,
    @SerializedName("is_verified") val isVerified: Boolean?,
    @SerializedName("verification_note") val verificationNote: String?,
)

data class ResearchEvidenceEnvelopeDto(val evidence: List<ResearchEvidenceDto>, val total: Int?)

// Memory

data class MemorySettingsDto(
    @SerializedName("short_term_enabled") val shortTermEnabled: Boolean,
    @SerializedName("mid_term_enabled") val midTermEnabled: Boolean,
    @SerializedName("conversation_summary_enabled") val conversationSummaryEnabled: Boolean,
    @SerializedName("research_memory_enabled") val researchMemoryEnabled: Boolean,
    @SerializedName("portfolio_memory_enabled") val portfolioMemoryEnabled: Boolean,
    @SerializedName("consent_required") val consentRequired: Boolean?,
    @SerializedName("retention_days") val retentionDays: Int?,
)

data class MemorySettingsEnvelopeDto(val settings: MemorySettingsDto)

data class MemorySettingsPatchRequest(
    @SerializedName("short_term_enabled") val shortTermEnabled: Boolean?,
    @SerializedName("mid_term_enabled") val midTermEnabled: Boolean?,
    @SerializedName("conversation_summary_enabled") val conversationSummaryEnabled: Boolean?,
    @SerializedName("research_memory_enabled") val researchMemoryEnabled: Boolean?,
    @SerializedName("portfolio_memory_enabled") val portfolioMemoryEnabled: Boolean?,
    @SerializedName("consent_granted") val consentGranted: Boolean,
)

data class MemoryItemDto(
    val id: String,
    val scope: String,
    val kind: String,
    @SerializedName("content_preview") val contentPreview: String,
    val status: String?,
    @SerializedName("created_at") val createdAt: String?,
)

data class MemoryItemsEnvelopeDto(val items: List<MemoryItemDto>, val total: Int?)

data class MemoryProposalDto(
    val id: String,
    val scope: String,
    @SerializedName("content_preview") val contentPreview: String,
    val source: String,
    val status: String,
)

data class MemoryProposalsEnvelopeDto(val proposals: List<MemoryProposalDto>)

// Trading mandates（只读 + 有限管理）

data class TradingMandateDto(
    val id: String,
    val name: String,
    @SerializedName("strategy_name") val strategyName: String?,
    val environment: String?,
    val paused: Boolean?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("updated_at") val updatedAt: String?,
    @SerializedName("last_run_at") val lastRunAt: String?,
    @SerializedName("last_run_status") val lastRunStatus: String?,
    @SerializedName("risk_block_reason") val riskBlockReason: String?,
)

data class TradingMandatesEnvelopeDto(val mandates: List<TradingMandateDto>)
data class TradingMandateEnvelopeDto(val mandate: TradingMandateDto)
