package ai.puregamma.android.data.repository

import ai.puregamma.android.data.local.ResponseCache
import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.dto.MarketAssetDto
import ai.puregamma.android.data.remote.dto.ReportDto
import ai.puregamma.android.model.MarketAsset
import ai.puregamma.android.model.Report
import com.google.gson.reflect.TypeToken

class CachedTodayRepository(
    private val api: PureGammaApi,
    private val cache: ResponseCache,
) {
    private val marketType = object : TypeToken<List<MarketAsset>>() {}
    private val reportsType = object : TypeToken<List<Report>>() {}

    suspend fun getMarketSnapshot(): Pair<List<MarketAsset>, Boolean> {
        return try {
            val dto = api.getMarketSnapshot()
            val assets = dto.assets?.map { it.toDomain() } ?: emptyList()
            cache.save(assets, "market-snapshot", marketType)
            assets to false
        } catch (e: Exception) {
            val cached = cache.loadStaleOrNull("market-snapshot", marketType) as? List<MarketAsset>
            if (cached != null) cached to true
            else throw e
        }
    }

    suspend fun getReports(): Pair<List<Report>, Boolean> {
        return try {
            val dto = api.getReports()
            val reports = dto.reports?.map { it.toDomain() } ?: emptyList()
            cache.save(reports, "reports", reportsType)
            reports to false
        } catch (e: Exception) {
            val cached = cache.loadStaleOrNull("reports", reportsType) as? List<Report>
            if (cached != null) cached to true
            else throw e
        }
    }

    suspend fun clearCache() = cache.clear()
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

private fun parseInstant(raw: String): java.time.Instant {
    return runCatching { java.time.Instant.parse(raw) }.getOrNull() ?: java.time.Instant.EPOCH
}
