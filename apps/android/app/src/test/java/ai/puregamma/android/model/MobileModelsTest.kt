package ai.puregamma.android.model

import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class MobileModelsTest {

    @Test
    fun capabilitiesParseServerPayload() {
        val json = JSONObject(
            """
            {
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
              "app_min_version": "1.4.0",
              "maintenance_message": null
            }
            """.trimIndent(),
        )
        val capabilities = json.toMobileCapabilities()
        assertTrue(capabilities.harnessResearchEnabled)
        assertTrue(capabilities.serverContractAvailable)
        assertFalse(capabilities.liveTradingEnabled)
        assertFalse(capabilities.userCanPauseMandates)
        assertEquals("1.4.0", capabilities.appMinVersion)
    }

    @Test
    fun capabilitiesTolerateMissingFields() {
        val json = JSONObject("""{"harness_research_enabled": true, "future_field": {"nested": [1,2]}}""")
        val capabilities = json.toMobileCapabilities()
        assertTrue(capabilities.harnessResearchEnabled)
        assertFalse(capabilities.memoryServiceEnabled)
        assertFalse(capabilities.autoTradingEnabled)
        assertTrue(capabilities.serverContractAvailable)
    }

    @Test
    fun capabilitiesDefaultUnavailableIsAllOff() {
        assertFalse(MobileCapabilities.UNAVAILABLE.harnessResearchEnabled)
        assertFalse(MobileCapabilities.UNAVAILABLE.serverContractAvailable)
    }

    @Test
    fun researchRunParsesEveryServerState() {
        for (raw in listOf("queued", "preparing", "running", "validating", "completed", "degraded", "failed", "canceled", "timed_out")) {
            val json = JSONObject("""{"id":"r1","name":"n","status":"$raw","verification":"verified","evidence_count":2,"is_degraded":false}""")
            assertEquals(raw.uppercase(), json.toResearchRun().state.name)
        }
    }

    @Test
    fun researchRunUnknownStateFallsBackToIdle() {
        val json = JSONObject("""{"id":"r1","name":"n","status":"brand_new_state"}""")
        assertEquals(ResearchRunState.IDLE, json.toResearchRun().state)
    }

    @Test
    fun researchRunDegradedFlagAndErrorParsed() {
        val json = JSONObject("""{"id":"r1","name":"n","status":"completed","is_degraded":true,"error_message":"partial evidence"}""")
        val run = json.toResearchRun()
        assertTrue(run.degraded)
        assertEquals("partial evidence", run.errorMessage)
    }

    @Test
    fun mandateEnvironmentParsing() {
        assertEquals(TradingEnvironment.PAPER, TradingEnvironment.fromServer("paper"))
        assertEquals(TradingEnvironment.SHADOW, TradingEnvironment.fromServer("shadow"))
        assertEquals(TradingEnvironment.LIVE_DISABLED, TradingEnvironment.fromServer("live_disabled"))
        assertEquals(TradingEnvironment.UNAVAILABLE, TradingEnvironment.fromServer("live"))
        assertEquals(TradingEnvironment.UNAVAILABLE, TradingEnvironment.fromServer(null))
    }

    @Test
    fun mandateUnknownFieldsIgnored() {
        val json = JSONObject("""{"id":"m1","name":"n","environment":"paper","paused":true,"risk_block_reason":"daily_loss_limit","future":42}""")
        val mandate = json.toTradingMandate()
        assertTrue(mandate.paused)
        assertEquals("daily_loss_limit", mandate.riskBlockReason)
    }

    @Test
    fun memorySettingsDefaultsWhenMissing() {
        val json = JSONObject("""{"short_term_enabled":true}""")
        val settings = json.toMemorySettings()
        assertTrue(settings.shortTermEnabled)
        assertTrue(settings.consentRequired)
        assertEquals(30, settings.retentionDays)
    }

    @Test
    fun memoryItemLifecycleParsing() {
        val mapping = mapOf(
            "saved" to MemoryItemLifecycle.SAVED,
            "pending" to MemoryItemLifecycle.PENDING,
            "rejected" to MemoryItemLifecycle.REJECTED,
            "expired" to MemoryItemLifecycle.EXPIRED,
            "deleted" to MemoryItemLifecycle.DELETED,
        )
        for ((raw, expected) in mapping) {
            val json = JSONObject("""{"id":"m1","scope":"mid_term","kind":"k","content_preview":"p","status":"$raw"}""")
            assertEquals(expected, json.toMemoryItem().lifecycle)
        }
    }

    @Test
    fun capabilitiesNeverFabricatedFromLocalDefaults() {
        // 本地默认值不能冒充服务端可用结论。
        assertNull(MobileCapabilities.UNAVAILABLE.appMinVersion)
        assertNull(MobileCapabilities.UNAVAILABLE.maintenanceMessage)
    }

    @Test
    fun userParsingToleratesMissingAndUnknownMembershipTier() {
        val missing = JSONObject(
            """{"id":"u1","email":"a@b.c","name":"A","role":"user","plan":"Pro","credit_balance":1}""",
        ).toUser()
        assertNull(missing.membershipTier)

        val unknown = JSONObject(
            """{"id":"u1","email":"a@b.c","name":"A","role":"user","plan":"Max","membership_tier":"diamond","credit_balance":1}""",
        ).toUser()
        // Unknown tier never crashes: it is carried as an opaque string and
        // the UI falls back to the plan label.
        assertEquals("diamond", unknown.membershipTier)

        val gold = JSONObject(
            """{"id":"u1","email":"a@b.c","name":"A","role":"user","plan":"Max","membership_tier":"gold","credit_balance":1}""",
        ).toUser()
        assertEquals("gold", gold.membershipTier)
    }
}
