package ai.puregamma.android.agent

import ai.puregamma.android.data.remote.ApiErrorDetail
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.data.remote.dto.LiveNavEnvelopeDto
import ai.puregamma.android.data.remote.dto.LiveNavHistoryDto
import ai.puregamma.android.data.remote.dto.ModelDto
import ai.puregamma.android.data.remote.dto.PortfolioDto
import ai.puregamma.android.data.repository.LiveNavRepository
import ai.puregamma.android.data.repository.toDomain
import ai.puregamma.android.model.AgentModel
import ai.puregamma.android.model.decimalOrNull
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException
import java.math.BigDecimal

/**
 * Each test decodes a real server response from docs/mobile/fixtures (pinned
 * by tests/contract/test_mobile_agent_contract.py) and checks the client rule
 * of docs/mobile/MOBILE_API_CONTRACT.md §8 that depends on it.
 */
class MobileContractFixtureTest {
    private val gson = Gson()

    private fun refusal(name: String): RetrofitApiException {
        val (status, body) = ContractFixtures.http(name)
        return RetrofitApiException.fromBody(status, body.toString())
    }

    // ---- (a) idempotent send

    @Test
    fun requestIdsMatchTheServerPattern() {
        val first = ClientRequestId.make()
        val second = ClientRequestId.make()
        assertTrue(ClientRequestId.isValid(first) && ClientRequestId.isValid(second))
        assertNotEquals(first, second)
        assertFalse(ClientRequestId.isValid("short"))
        assertFalse(ClientRequestId.isValid("has spaces in it"))
    }

    @Test
    fun retryReusesTheIdUntilTheServerAcceptedTheAttempt() {
        val attempt = AgentSendAttempt(content = "q", model = "default")
        assertEquals(attempt.requestId, attempt.forRetry().requestId)
        val accepted = attempt.copy(accepted = true)
        assertNotEquals(attempt.requestId, accepted.forRetry().requestId)
    }

    @Test
    fun duplicateSubmissionKeepsTheOriginalRun() {
        val error = refusal("agent_send_duplicate_409.json")
        assertEquals("DUPLICATE_SUBMISSION", error.code)
        assertEquals("00000000-0000-4000-8000-000000000001", error.detail?.fields?.get("runId"))
        assertTrue(error.detail?.fields?.containsKey("messageId") == true)
        val failure = AgentSendFailure.classify(error)
        assertTrue(failure is AgentSendFailure.Duplicate)
        assertEquals("00000000-0000-4000-8000-000000000001", (failure as AgentSendFailure.Duplicate).runId)
    }

    @Test
    fun sendRefusalsKeepTheirCodeAndAreClassified() {
        val expected = mapOf(
            "agent_send_limit_429.json" to "retryable",
            "agent_send_insufficient_credits_402.json" to "final",
            "agent_send_model_invalid_400.json" to "final",
            "agent_send_model_plan_required_403.json" to "final",
            "agent_send_model_unavailable_503.json" to "retryable",
            "agent_send_model_pricing_503.json" to "final",
        )
        for ((name, kind) in expected) {
            val error = refusal(name)
            assertTrue("$name lost its code", error.code != null)
            val failure = AgentSendFailure.classify(error)
            assertEquals(name, kind, if (failure is AgentSendFailure.Retryable) "retryable" else if (failure is AgentSendFailure.Final) "final" else "other")
        }
        assertTrue(AgentSendFailure.classify(IOException("offline")) is AgentSendFailure.Retryable)
    }

    // ---- (b) permission modes

    @Test
    fun onlyReadOnlyAndWorkspaceWriteAreOffered() {
        val body = ContractFixtures.http("agent_workspace_capabilities.json").second
        val modes = body.getAsJsonArray("permission_modes").map { it.asString }
        assertEquals(listOf(AgentPermissionMode.READ_ONLY, AgentPermissionMode.WORKSPACE_WRITE), AgentPermissionMode.selectable(modes))
        assertEquals(listOf(AgentPermissionMode.READ_ONLY), AgentPermissionMode.selectable(listOf("read-only", "full-access")))
        assertEquals("FULL_ACCESS_ACKNOWLEDGEMENT_REQUIRED", refusal("agent_permission_full_access_400.json").code)
        assertEquals("CONVERSATION_BUSY", refusal("agent_permission_busy_409.json").code)
    }

    // ---- (c)(e) NAV and decimal money

    @Test
    fun navWithoutAnAccountIsAnEmptyStateNotZero() {
        for (name in listOf("portfolio_nav_no_account_404.json", "portfolio_nav_history_no_account_404.json", "portfolio_positions_no_account_404.json")) {
            assertTrue(name, LiveNavRepository.isNoAccount(refusal(name)))
        }
        assertFalse(LiveNavRepository.isNoAccount(refusal("agent_conversation_deleted_404.json")))
    }

    @Test
    fun navAmountsAreExactDecimals() {
        val envelope = gson.fromJson(ContractFixtures.body("portfolio_nav_200.json"), LiveNavEnvelopeDto::class.java)
        val nav = envelope.nav.toDomain(envelope.dailyPnl, envelope.dailyReturn)
        assertEquals(BigDecimal("101234.56789012"), nav.nav)
        assertEquals(BigDecimal("-1.00000001"), nav.netExposure)
        assertEquals(0, BigDecimal.ZERO.compareTo(nav.realizedPnl))
        assertEquals(BigDecimal("1234.56789012"), nav.dailyPnl)
        assertTrue(nav.calculatedAt != null) // a naive timestamp is read as UTC
        val history = gson.fromJson(ContractFixtures.body("portfolio_nav_history_200.json"), LiveNavHistoryDto::class.java)
        assertEquals(listOf(BigDecimal("101234.56789012"), BigDecimal("100000.00000000")), history.history!!.map { it.toDomain(null, null).nav })
        val unpriced = gson.fromJson("""{"nav":{"nav":null,"cash":"1.5","is_stale":true},"daily_pnl":null,"daily_return":null}""", LiveNavEnvelopeDto::class.java)
        assertNull(unpriced.nav.toDomain(null, null).nav)
    }

    @Test
    fun legacyPortfolioNumbersBecomeExactDecimalsToo() {
        val dto = gson.fromJson("""{"connected":true,"nav":101234.56789012,"available_cash":"25000.50","nav_history":[{"date":"2026-10-29T00:00:00Z","nav":0.1}]}""", PortfolioDto::class.java)
        assertEquals(BigDecimal("101234.56789012"), decimalOrNull(dto.nav))
        assertEquals(BigDecimal("25000.50"), decimalOrNull(dto.availableCash))
        assertEquals(BigDecimal("0.1"), decimalOrNull(dto.navHistory!!.single().nav))
        assertNull(decimalOrNull("0E-8x"))
    }

    // ---- (d) deleted conversation

    @Test
    fun deletedConversationIsRecognised() {
        val error = refusal("agent_conversation_deleted_404.json")
        assertNull(error.code)
        assertEquals("Conversation not found", error.message)
        assertEquals(AgentSendFailure.ConversationGone, AgentSendFailure.classify(error))
    }

    @Test
    fun codedNotFoundOnSendIsARefusalNotADeletedConversation() {
        // POST /api/agent/conversations/{id}/messages answers SKILL_NOT_FOUND as a coded 404.
        val skill = RetrofitApiException.fromBody(404, """{"detail":{"code":"SKILL_NOT_FOUND","message":"Skill not found"}}""")
        assertTrue(AgentSendFailure.classify(skill) is AgentSendFailure.Final)
        // The rate limiter's bare 429 clears with time.
        val limited = RetrofitApiException.fromBody(429, """{"detail":"Rate limit exceeded"}""")
        assertTrue(AgentSendFailure.classify(limited) is AgentSendFailure.Retryable)
    }

    // ---- (f) model menu

    @Test
    fun modelMenuHidesEvaluationAndExplainsUnavailableModels() {
        val body = ContractFixtures.http("agent_capabilities_models.json").second
        val type = object : TypeToken<List<ModelDto>>() {}.type
        val dtos: List<ModelDto> = gson.fromJson(body.getAsJsonArray("models"), type)
        val models = dtos.map { AgentModel(it.id, it.displayName, it.provider, it.available, it.reason, it.category ?: "generation") }
        val menu = AgentModelMenu.entries(models)
        assertFalse(menu.any { it.id == "jev" })
        assertEquals(listOf("default"), menu.filter { it.selectable }.map { it.id })
        assertEquals("pricing_not_configured", menu.first { it.id == "gpt-6-sol" }.reason)
        assertEquals("plan_required", menu.first { it.id == "gpt-5.6-luna" }.reason)
        assertEquals("default", AgentModelMenu.resolve("gpt-6-sol", models))
        assertEquals("default", AgentModelMenu.resolve("jev", models))
        assertEquals("default", AgentModelMenu.resolve(null, models))
    }

    // ---- (g) frames, cursor, replay

    @Test
    fun cursorDropsReplayedAndForeignFrames() {
        val cursor = AgentRunCursor()
        val started = AgentFrame("run.started", 1, "r1", AgentStreamEvent.RunStarted("r1", "m1"))
        assertTrue(cursor.admit(started))
        assertEquals("r1", cursor.runId)
        assertFalse(cursor.admit(started))
        assertTrue(cursor.admit(AgentFrame("message.delta", 2, null, AgentStreamEvent.Delta("m1", "x"))))
        assertFalse(cursor.admit(AgentFrame("tool.started", 3, "other", AgentStreamEvent.ToolStarted("t"))))
        assertTrue(cursor.admit(AgentFrame("message.completed", 4, "r1", AgentStreamEvent.Completed("m1"))))
        assertEquals(4, cursor.lastSeq)
    }

    @Test
    fun unknownFrameTypesAreIgnored() {
        val frame = AgentFrame.parse("workspace.preview", JsonObject())
        assertEquals(AgentStreamEvent.Ignored("workspace.preview"), frame.event)
        assertFalse(frame.event.isTerminal)
        assertEquals(AgentStreamEvent.Canceled, AgentFrame.parse("run.canceled", JsonObject()).event)
        assertTrue(AgentStreamEvent.Canceled.isTerminal)
    }

    @Test
    fun replayPagesParseForEveryStatus() {
        for (status in listOf("running", "canceled", "interrupted")) {
            val page = AgentRunEventsPage.parse(ContractFixtures.http("agent_run_events_$status.json").second)
            assertEquals(status, page.status)
            assertEquals(if (status == "canceled") listOf(2, 3, 5, 6) else listOf(2, 3, 5), page.events.map { it.seq })
            assertEquals(page.events.last().seq, page.lastSeq)
            assertEquals(status != "running", AgentRunStatus.isTerminal(status))
            assertEquals(status == "canceled", page.events.last().event == AgentStreamEvent.Canceled)
        }
    }

    @Test
    fun followerWaitsThroughNetworkErrorsUntilTheServerSaysDone() = runTest {
        val running = AgentRunEventsPage.parse(ContractFixtures.http("agent_run_events_running.json").second)
        val calls = mutableListOf<Int>()
        val follower = AgentRunFollower(fetch = { _, after ->
            calls += after
            when (calls.size) {
                1 -> throw IOException("offline")
                2 -> running
                else -> running.copy(status = "completed")
            }
        }, pause = {})
        val applied = mutableListOf<Int?>()
        val result = follower.follow(running.runId, AgentRunCursor(running.runId, 1)) { applied += it.seq }
        assertEquals(AgentFollowResult.Finished("completed"), result)
        assertEquals(listOf(1, 1, 5), calls)
        assertEquals(listOf(2, 3, 5), applied)
    }

    @Test
    fun followerStopsOnAnotherUsersRun() = runTest {
        val follower = AgentRunFollower(fetch = { _, _ -> throw refusal("agent_run_events_not_found_404.json") }, pause = {})
        assertEquals(AgentFollowResult.NotFound, follower.follow("r", AgentRunCursor()) {})
    }

    @Test
    fun errorEnvelopeShapes() {
        assertEquals(ApiErrorDetail(422, null, "field required"), ApiErrorDetail.parse(422, """{"detail":[{"loc":["body"],"msg":"field required"}]}"""))
        assertEquals(ApiErrorDetail(500, null, null), ApiErrorDetail.parse(500, "<html>"))
        val structured = ApiErrorDetail.parse(402, """{"detail":{"code":"INSUFFICIENT_CREDITS","required":8}}""")
        assertEquals("INSUFFICIENT_CREDITS", structured.code)
        assertEquals("8", structured.fields["required"])
    }
}
