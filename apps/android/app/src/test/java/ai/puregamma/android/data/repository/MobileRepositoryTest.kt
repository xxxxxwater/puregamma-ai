package ai.puregamma.android.data.repository

import ai.puregamma.android.data.remote.PureGammaApi
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.model.MobileCapabilities
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
 * 能力发现与 Repository 层门控测试：服务端为准；404/501 → 全部不可用；
 * capabilities 为 false 时 Repository 不发任何网络请求；LIVE 操作在 Repository 层拦截。
 */
class MobileRepositoryTest {

    private lateinit var server: MockWebServer
    private lateinit var repository: MobileRepository
    private lateinit var capabilities: MobileCapabilities

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
        capabilities = MobileCapabilities()
        repository = MobileRepository(api) { capabilities }
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun enableContract() {
        capabilities = capabilities.copy(serverContractAvailable = true)
    }

    private fun enableResearch() {
        enableContract()
        capabilities = capabilities.copy(harnessResearchEnabled = true, userCanStartResearch = true, harnessRetryEnabled = true)
    }

    private fun enableMemory() {
        enableContract()
        capabilities = capabilities.copy(memoryServiceEnabled = true, userCanManageMemory = true)
    }

    private fun enableMandates() {
        enableContract()
        capabilities = capabilities.copy(autoTradingEnabled = true, userCanViewTradingMandates = true, userCanPauseMandates = true)
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
        val parsed = repository.getCapabilities()
        assertTrue(parsed.serverContractAvailable)
        assertTrue(parsed.harnessResearchEnabled)
        assertFalse(parsed.liveTradingEnabled)
    }

    @Test
    fun capabilities404MeansContractMissingNotCrash() = runTest {
        server.enqueue(MockResponse().setResponseCode(404).setBody("""{"detail":"not found"}"""))
        val parsed = repository.getCapabilities()
        assertFalse(parsed.serverContractAvailable)
        assertFalse(parsed.harnessResearchEnabled)
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

    // ---- Repository 层门控：capabilities 为 false 时不得发起网络请求 ----

    @Test
    fun researchBlockedWhenContractMissingWithoutNetwork() = runTest {
        try {
            repository.getResearchRuns()
            fail("Expected MobileFeatureException")
        } catch (e: MobileFeatureException) {
            assertEquals(MobileFeatureException.Kind.CONTRACT_MISSING, e.kind)
        }
        assertEquals(0, server.requestCount)
    }

    @Test
    fun researchBlockedWhenFlagFalseWithoutNetwork() = runTest {
        enableContract()
        try {
            repository.getResearchRun("r1")
            fail("Expected MobileFeatureException")
        } catch (e: MobileFeatureException) {
            assertEquals(MobileFeatureException.Kind.DISABLED, e.kind)
        }
        assertEquals(0, server.requestCount)
    }

    @Test
    fun memoryBlockedWhenDisabledWithoutNetwork() = runTest {
        enableContract()
        try {
            repository.getMemorySettings()
            fail("Expected MobileFeatureException")
        } catch (e: MobileFeatureException) {
            assertEquals(MobileFeatureException.Kind.DISABLED, e.kind)
        }
        assertEquals(0, server.requestCount)
    }

    @Test
    fun invalidIdsRejectedWithoutNetwork() = runTest {
        enableResearch()
        for (bad in listOf("", "../etc", "a b", "x/y", "run?x=1", "http://evil")) {
            try {
                repository.getResearchRun(bad)
                fail("Expected MobileFeatureException for id '$bad'")
            } catch (e: MobileFeatureException) {
                assertEquals(MobileFeatureException.Kind.INVALID_INPUT, e.kind)
            }
        }
        assertEquals(0, server.requestCount)
    }

    @Test
    fun createResearchRunFiltersDataSourceWhitelist() = runTest {
        enableResearch()
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"run":{"id":"r1","name":"n","status":"queued"}}"""))
        repository.createResearchRun("name", "prompt", listOf("market", "exchange_private", "all"))
        val request = server.takeRequest()
        val body = request.body.readUtf8()
        assertTrue(body.contains("\"market\""))
        assertFalse(body.contains("exchange_private"))
    }

    // ---- Mandate：LIVE 在 Repository 层恒不可操作 ----

    @Test
    fun liveMandatePauseBlockedInRepositoryWithoutPost() = runTest {
        enableMandates()
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"mandate":{"id":"m1","name":"n","strategy_name":"s","environment":"live_disabled","paused":true}}""",
            ),
        )
        try {
            repository.pauseMandate("m1")
            fail("Expected MobileFeatureException")
        } catch (e: MobileFeatureException) {
            assertEquals(MobileFeatureException.Kind.LIVE_DISABLED, e.kind)
        }
        assertEquals(1, server.requestCount) // 仅一次 GET，未发 pause POST
    }

    @Test
    fun paperPauseSendsRequestAndIdempotentWhenPaused() = runTest {
        enableMandates()
        // 第一次：GET mandate (paused=false) + POST pause 成功
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"mandate":{"id":"m1","name":"n","strategy_name":"s","environment":"paper","paused":false}}""",
            ),
        )
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"mandate":{"id":"m1","name":"n","strategy_name":"s","environment":"paper","paused":true}}""",
            ),
        )
        val paused = repository.pauseMandate("m1")
        assertTrue(paused.paused)
        // 第二次：已暂停 → 幂等返回，不新增请求
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                """{"mandate":{"id":"m1","name":"n","strategy_name":"s","environment":"paper","paused":true}}""",
            ),
        )
        val again = repository.pauseMandate("m1")
        assertTrue(again.paused)
        assertEquals(3, server.requestCount) // GET + POST + GET，无第二个 POST
    }

    @Test
    fun mandatesParseEnvironment() = runTest {
        enableMandates()
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
        enableResearch()
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
