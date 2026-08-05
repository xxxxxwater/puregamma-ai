package ai.puregamma.android.model

import org.json.JSONArray
import org.json.JSONObject
import java.time.Instant

data class User(
    val id: String,
    val email: String,
    val name: String,
    val role: String,
    val plan: String,
    val credits: Int,
    val avatarUrl: String?,
)

data class MarketAsset(
    val symbol: String,
    val price: Double,
    val volume24h: Double,
    val change24h: Double?,
    val fundingRate: Double?,
    val openInterest: Double?,
    val riskScore: Double?,
    val timestamp: Instant?,
    val source: String,
    val realtime: Boolean,
)

data class Report(
    val id: String,
    val title: String,
    val type: String,
    val markdown: String,
    val assets: List<String>,
    val createdAt: Instant?,
)

data class BillingSummary(
    val plan: String,
    val status: String,
    val credits: Int,
)

data class AgentConversation(
    val id: String,
    val title: String,
    val status: String,
    val summary: String?,
    val updatedAt: Instant?,
)

data class AgentSource(
    val index: Int,
    val provider: String,
    val title: String,
    val url: String?,
)

data class AgentMessage(
    val id: String,
    val conversationId: String,
    val role: String,
    val content: String,
    val status: String,
    val sources: List<AgentSource> = emptyList(),
    val error: String? = null,
)

data class AgentModel(
    val id: String,
    val name: String,
    val provider: String,
    val available: Boolean,
    val reason: String?,
)

data class AgentCapabilities(
    val plan: String,
    val dataSources: List<String>,
    val dailyRuns: Int,
    val concurrentRuns: Int,
    val credits: Int,
    val remaining: Int,
    val models: List<AgentModel>,
)

data class PortfolioConnection(
    val id: String,
    val provider: String,
    val name: String,
    val status: String,
    val lastSync: Instant?,
    val error: String?,
)

data class Portfolio(
    val connected: Boolean,
    val stale: Boolean,
    val asOf: Instant?,
    val nav: Double?,
    val availableCash: Double?,
    val connections: List<PortfolioConnection>,
    val navHistory: List<NavPoint> = emptyList(),
)

data class NavPoint(
    val date: Instant,
    val value: Double,
)

data class OptionCandidate(
    val instrument: String,
    val underlying: String,
    val type: String,
    val strike: Double?,
    val markIv: Double?,
    val gamma: Double?,
    val theta: Double?,
    val score: Double?,
    val expiry: Instant?,
    val timestamp: Instant?,
    val rationale: List<String>,
)

data class AutopilotFinding(val severity: String, val title: String)

data class Autopilot(
    val enabled: Boolean,
    val cadence: String,
    val autoSync: Boolean,
    val riskAlerts: Boolean,
    val longGammaWatch: Boolean,
    val delivery: String,
    val accountCount: Int,
    val findings: List<AutopilotFinding>,
    val lastReview: Instant?,
)

internal fun JSONObject.toUser(): User = User(
    id = string("id"),
    email = string("email"),
    name = string("name"),
    role = string("role"),
    plan = string("plan"),
    credits = optInt("credit_balance"),
    avatarUrl = nullableString("avatar_url"),
)

internal fun JSONObject.toMarketAsset(): MarketAsset = MarketAsset(
    symbol = string("symbol"),
    price = optDouble("price"),
    volume24h = optDouble("volume_24h"),
    change24h = nullableDouble("change_24h"),
    fundingRate = nullableDouble("funding_rate"),
    openInterest = nullableDouble("open_interest"),
    riskScore = nullableDouble("risk_score"),
    timestamp = instant("timestamp"),
    source = nullableString("source_display") ?: nullableString("source") ?: "-",
    realtime = optBoolean("is_realtime"),
)

internal fun JSONObject.toReport(): Report = Report(
    id = string("id"),
    title = string("title"),
    type = string("report_type"),
    markdown = string("content_markdown"),
    assets = optJSONArray("assets").strings(),
    createdAt = instant("created_at"),
)

internal fun JSONObject.toConversation(): AgentConversation = AgentConversation(
    id = string("id"),
    title = string("title"),
    status = string("status"),
    summary = nullableString("summary"),
    updatedAt = instant("updated_at"),
)

internal fun JSONObject.toMessage(): AgentMessage = AgentMessage(
    id = string("id"),
    conversationId = string("conversation_id"),
    role = string("role"),
    content = string("content"),
    status = string("status"),
    sources = optJSONArray("sources").objects().map { source ->
        AgentSource(
            index = source.optInt("citation_index"),
            provider = source.string("provider"),
            title = source.string("title"),
            url = source.nullableString("url"),
        )
    },
    error = nullableString("error_message"),
)

internal fun JSONObject.toPortfolio(): Portfolio = Portfolio(
    connected = optBoolean("connected"),
    stale = optBoolean("stale"),
    asOf = instant("data_as_of"),
    nav = nullableDouble("nav"),
    availableCash = nullableDouble("available_cash"),
    connections = optJSONArray("connections").objects().map {
        PortfolioConnection(
            id = it.string("id"),
            provider = it.string("provider"),
            name = it.string("name"),
            status = it.string("status"),
            lastSync = it.instant("last_sync"),
            error = it.nullableString("error"),
        )
    },
)

internal fun JSONObject.toAutopilot(): Autopilot {
    val config = optJSONObject("config") ?: JSONObject()
    return Autopilot(
        enabled = config.optBoolean("enabled"),
        cadence = config.string("cadence"),
        autoSync = config.optBoolean("auto_sync"),
        riskAlerts = config.optBoolean("risk_alerts"),
        longGammaWatch = config.optBoolean("long_gamma_watch"),
        delivery = config.string("delivery"),
        accountCount = optInt("account_count"),
        findings = optJSONArray("findings").objects().map {
            AutopilotFinding(it.string("severity"), it.string("title"))
        },
        lastReview = instant("last_review"),
    )
}

internal fun JSONObject.string(key: String): String = optString(key, "")
internal fun JSONObject.nullableString(key: String): String? =
    if (!has(key) || isNull(key)) null else optString(key).takeIf { it.isNotBlank() }
internal fun JSONObject.nullableDouble(key: String): Double? =
    if (!has(key) || isNull(key)) null else optDouble(key)
internal fun JSONObject.instant(key: String): Instant? = nullableString(key)?.let {
    runCatching { Instant.parse(it) }.getOrNull()
}
internal fun JSONArray?.objects(): List<JSONObject> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optJSONObject(it) }
internal fun JSONArray?.strings(): List<String> =
    if (this == null) emptyList() else (0 until length()).mapNotNull { optString(it).takeIf(String::isNotBlank) }
