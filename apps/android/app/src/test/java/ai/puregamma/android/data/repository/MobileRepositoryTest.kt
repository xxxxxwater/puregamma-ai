package ai.puregamma.android.data.repository

import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.model.TradingEnvironment
import com.google.gson.GsonBuilder
import kotlinx.coroutines.test.runTest
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

/**
 * 能力发现契约测试：服务端为准；404/501 → 全部不可用；5xx 抛出而非本地放行。
 */
class MobileRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: MobileRepository

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        val gson = GsonBuilder().serializeNulls().create()
        val api = Retrofit.Builder()
            .baseUrl(server.url("/"))
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(PureGammaApi::class.java)
        repository = MobileRepository(api)
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun capabilitiesParseServerPayload() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{
                  "harness_research_enabled": true,
                  "memory_service_enabled": true,
                  "auto_trading_enabled": false,
                  "paper_trading_enabled": false,
                  "shadow_trading_enabled": false,
                  "live_trading_enabled": false,
                  "user_can_start_research": true,
                  "user_can_manage_memory": true,
                  "user_can_view_trading_mandates": true,
                  "user_can_pause_mandates": false,
                  "harness_retry_enabled": true,
                  "app_min_version": "1.4.0"
                }""",
            ),
        )
        val capabilities = repository.getCapabilities()
        assertTrue(capabilities.serverContractAvailable)
        assertTrue(capabilities.harnessResearchEnabled)
        assertFalse(capabilities.liveTradingEnabled)
    }

    @Test
    fun capabilities404MeansContractMissingNotCrash() = runTest {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"detail":"not found"}"""))
        val capabilities = repository.getCapabilities()
        assertFalse(capabilities.serverContractAvailable)
        assertFalse(capabilities.harnessResearchEnabled)
    }

    @Test
    fun capabilities501MeansContractMissing() = runTest {
        server.enqueue(MockResponse().setResponseCode(501).setBody("""{"detail":"not implemented"}"""))
        assertFalse(repository.getCapabilities().serverContractAvailable)
    }

    @Test
    fun capabilities500ThrowsInsteadOfLocalFallback() = runTest {
        server.enqueue(MockResponse().setResponseCode(500).setBody("""{"detail":"boom"}"""))
        try {
            repository.getCapabilities()
            fail("Expected RetrofitApiException")
        } catch (e: RetrofitApiException) {
            assertEquals(500, e.status)
        }
    }

    @Test
    fun mandatesParseEnvironment() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"mandates":[{"id":"m1","name":"BTC Long Gamma","strategy_name":"long_gamma_v1",
                   "environment":"live_disabled","paused":true,"risk_block_reason":"daily_loss_limit"}]}""",
            ),
        )
        val mandates = repository.getTradingMandates()
        assertEquals(1, mandates.size)
        assertEquals(TradingEnvironment.LIVE_DISABLED, mandates[0].environment)
        assertTrue(mandates[0].environment.isLive)
    }

    @Test
    fun researchRuns404SurfacesAsExceptionForUnavailableUI() = runTest {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"detail":"not found"}"""))
        try {
            repository.getResearchRuns()
            fail("Expected RetrofitApiException")
        } catch (e: RetrofitApiException) {
            // UI 据此显示"功能暂不可用"，绝不使用假数据。
            assertEquals(404, e.status)
        }
    }
}
