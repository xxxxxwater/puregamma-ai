package ai.puregamma.android.data.remote.dto

import com.google.gson.annotations.SerializedName

data class UserDto(
    val id: String,
    val email: String,
    val name: String,
    val role: String,
    val plan: String,
    @SerializedName("credit_balance") val creditBalance: Int,
    @SerializedName("avatar_url") val avatarUrl: String?,
    val locale: String?
)

data class UserEnvelopeDto(val user: UserDto)

data class EmailLoginRequest(
    val email: String,
    val password: String,
)

data class EmailRegisterRequest(
    val email: String,
    val password: String,
    val name: String,
    val locale: String,
)

data class AuthResponseDto(
    @SerializedName("access_token") val accessToken: String,
    val user: UserDto,
)

data class GoogleOAuthStartRequest(
    @SerializedName("redirect_uri") val redirectUri: String,
    @SerializedName("code_challenge") val codeChallenge: String,
    @SerializedName("client_state") val clientState: String,
    val nonce: String,
)

data class GoogleOAuthStartResponseDto(
    @SerializedName("auth_url") val authUrl: String,
)

data class GoogleOAuthExchangeRequest(
    val code: String,
    @SerializedName("code_verifier") val codeVerifier: String,
    val nonce: String,
)

data class MarketAssetDto(
    val symbol: String,
    val price: Double,
    @SerializedName("volume_24h") val volume24h: Double,
    @SerializedName("change_24h") val change24h: Double?,
    @SerializedName("funding_rate") val fundingRate: Double?,
    @SerializedName("open_interest") val openInterest: Double?,
    @SerializedName("risk_score") val riskScore: Double?,
    val timestamp: String?,
    @SerializedName("source_display") val sourceDisplay: String?,
    val source: String?,
    @SerializedName("is_realtime") val isRealtime: Boolean?,
)

data class MarketEnvelopeDto(val assets: List<MarketAssetDto>)

data class ReportDto(
    val id: String,
    val title: String,
    @SerializedName("report_type") val reportType: String,
    @SerializedName("content_markdown") val contentMarkdown: String,
    val assets: List<String>,
    @SerializedName("created_at") val createdAt: String?,
)

data class ReportsEnvelopeDto(val reports: List<ReportDto>)

data class SubscriptionDto(
    val plan: String,
    @SerializedName("subscription_status") val subscriptionStatus: String,
    @SerializedName("credit_balance") val creditBalance: Int,
    @SerializedName("current_period_end") val currentPeriodEnd: String?,
    @SerializedName("cancel_at_period_end") val cancelAtPeriodEnd: Boolean?,
    val entitlement: EntitlementDto,
)

data class EntitlementDto(
    @SerializedName("allowed_data_sources") val allowedDataSources: List<String>?,
)

data class NavPointDto(
    val date: String,
    val nav: Double,
)

data class PortfolioConnectionDto(
    val id: String,
    val provider: String,
    val name: String,
    val status: String,
    @SerializedName("last_sync") val lastSync: String?,
    val error: String?,
)

data class PortfolioProvidersDto(
    val plaid: Boolean,
    val ibkr: Boolean,
    val hyperliquid: Boolean,
)

data class PortfolioDto(
    val connected: Boolean,
    val stale: Boolean?,
    @SerializedName("data_as_of") val dataAsOf: String?,
    val nav: Double?,
    @SerializedName("available_cash") val availableCash: Double?,
    @SerializedName("nav_history") val navHistory: List<NavPointDto>?,
    val connections: List<PortfolioConnectionDto>?,
    val providers: PortfolioProvidersDto?,
)

data class PlaidLinkTokenDto(
    @SerializedName("link_token") val linkToken: String,
)

data class IbkrOAuthStartRequest(
    @SerializedName("redirect_uri") val redirectUri: String,
)

data class IbkrOAuthStartResponseDto(
    @SerializedName("authorize_url") val authorizeUrl: String,
)

data class IbkrOAuthCompleteRequest(val code: String)

data class AutopilotConfigDto(
    val enabled: Boolean,
    val cadence: String,
    @SerializedName("auto_sync") val autoSync: Boolean,
    @SerializedName("risk_alerts") val riskAlerts: Boolean,
    @SerializedName("long_gamma_watch") val longGammaWatch: Boolean,
    val delivery: String,
)

data class AutopilotFindingDto(val severity: String, val title: String)

data class AutopilotDto(
    val config: AutopilotConfigDto,
    @SerializedName("account_count") val accountCount: Int,
    val findings: List<AutopilotFindingDto>,
    @SerializedName("last_review") val lastReview: String?,
)

data class ConversationDto(
    val id: String,
    val title: String,
    val status: String,
    val summary: String?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("updated_at") val updatedAt: String?,
    @SerializedName("archived_at") val archivedAt: String?,
)

data class ConversationEnvelopeDto(val conversation: ConversationDto)

data class ConversationsEnvelopeDto(val conversations: List<ConversationDto>)

data class MessageDto(
    val id: String,
    @SerializedName("conversation_id") val conversationId: String,
    val role: String,
    val content: String,
    val status: String,
    val model: String?,
    val sources: List<SourceDto>?,
    @SerializedName("created_at") val createdAt: String?,
    @SerializedName("error_message") val errorMessage: String?,
)

data class SourceDto(
    val id: String?,
    val provider: String,
    val title: String,
    val url: String?,
    @SerializedName("published_at") val publishedAt: String?,
    @SerializedName("source_timestamp") val sourceTimestamp: String?,
    @SerializedName("fetched_at") val fetchedAt: String?,
    @SerializedName("citation_index") val citationIndex: Int,
)

data class ConversationDetailDto(
    val conversation: ConversationDto,
    val messages: List<MessageDto>,
)

data class ConversationPatchRequest(
    val title: String?,
    val archived: Boolean?,
)

data class CapabilitiesDto(
    val plan: String,
    @SerializedName("allowed_data_sources") val allowedDataSources: List<String>,
    @SerializedName("agent_daily_runs") val agentDailyRuns: Int,
    @SerializedName("agent_concurrent_runs") val agentConcurrentRuns: Int,
)

data class QuotaDto(
    val remaining: Int,
    @SerializedName("credit_balance") val creditBalance: Int,
)

data class ModelDto(
    val id: String,
    @SerializedName("display_name") val displayName: String,
    val description: String?,
    val provider: String,
    val available: Boolean,
    val reason: String?,
)

data class CapabilitiesEnvelopeDto(
    val capabilities: CapabilitiesDto,
    val quota: QuotaDto,
    val models: List<ModelDto>,
)

data class AgentMessageRequest(val content: String, val locale: String, @SerializedName("data_sources") val dataSources: List<String>, val skills: List<String>, @SerializedName("custom_prompt") val customPrompt: String, val attachments: List<AgentAttachmentRequest>, val model: String)

data class AgentAttachmentRequest(val name: String, val content: String, val mime: String)

data class LongGammaEnvelopeDto(
    val status: String,
    val provider: String?,
    val currency: String?,
    @SerializedName("fetched_at") val fetchedAt: String?,
    val candidates: List<OptionCandidateDto>?,
    val error: String?,
)

data class OptionCandidateDto(
    val instrument: String,
    val underlying: String,
    @SerializedName("option_type") val optionType: String,
    val strike: Double?,
    @SerializedName("mark_iv") val markIv: Double?,
    val expiry: String?,
    val timestamp: String?,
    val greeks: GreeksDto?,
    @SerializedName("research_score") val researchScore: Double?,
    val rationale: List<String>?,
)

data class GreeksDto(val gamma: Double?, val theta: Double?)

data class DailyPushDto(
    val enabled: Boolean,
    val timezone: String,
    @SerializedName("local_time") val localTime: String,
    val channel: String,
    val locale: String,
    @SerializedName("include_portfolio") val includePortfolio: Boolean,
    @SerializedName("include_market") val includeMarket: Boolean,
    @SerializedName("include_signals") val includeSignals: Boolean,
    @SerializedName("include_risk") val includeRisk: Boolean,
    @SerializedName("include_sentiment") val includeSentiment: Boolean,
    @SerializedName("next_delivery_at") val nextDeliveryAt: String?,
)

data class DailyPushEnvelopeDto(val preference: DailyPushDto)

data class PushDeviceRequestDto(
    val token: String,
    val environment: String = "android",
    val locale: String,
    val timezone: String,
)

data class PushDeviceRegistrationDto(
    @SerializedName("delivery_available") val deliveryAvailable: Boolean,
)
