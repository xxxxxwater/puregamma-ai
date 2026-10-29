package ai.puregamma.android.agent

import ai.puregamma.android.data.remote.SseClient
import com.google.gson.JsonParser
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.SocketPolicy
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * One Agent turn end to end over a real HTTP stream (MockWebServer), with the
 * replay log and conversation snapshot served from the contract fixtures.
 */
class AgentTurnRunnerTest {
    private lateinit var server: MockWebServer
    private lateinit var sse: SseClient
    private val replayCalls = mutableListOf<Pair<String, Int>>()
    private var replayPages: (String, Int) -> AgentRunEventsPage = { _, _ -> error("no replay expected") }
    private var activeRun: String? = null

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        sse = SseClient(OkHttpClient(), baseUrl = server.url("/").toString())
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    private fun runner() = AgentTurnRunner(
        openStream = { conversationId, attempt, onOpen, onEvent ->
            sse.stream("/api/agent/conversations/$conversationId/messages", mapOf("content" to attempt.content, "client_request_id" to attempt.requestId), onOpen, onEvent)
        },
        follower = AgentRunFollower(fetch = { runId, after -> replayCalls += runId to after; replayPages(runId, after) }, pause = {}),
        activeRunId = { activeRun },
    )

    private fun page(name: String, status: String? = null): AgentRunEventsPage {
        val parsed = AgentRunEventsPage.parse(ContractFixtures.http(name).second)
        return if (status == null) parsed else parsed.copy(status = status)
    }

    private fun json(name: String) = MockResponse().setResponseCode(ContractFixtures.http(name).first)
        .setHeader("Content-Type", "application/json").setBody(ContractFixtures.body(name))

    private suspend fun turn(attempt: AgentSendAttempt = AgentSendAttempt("What moved BTC today?", "default")): Triple<AgentTurnOutcome, List<AgentFrame>, Boolean> {
        val applied = mutableListOf<AgentFrame>()
        var recovering = false
        val outcome = runner().run("c1", attempt, AgentRunCursor(), onAccepted = {}, onRecovering = { recovering = true }) { applied += it }
        return Triple(outcome, applied, recovering)
    }

    @Test
    fun theRequestCarriesTheAttemptsRequestId() = runTest {
        server.enqueue(MockResponse().setBody(ContractFixtures.text("agent_send_stream_completed.sse")))
        val attempt = AgentSendAttempt("q", "default")
        turn(attempt)
        val sent = JsonParser.parseString(server.takeRequest().body.readUtf8()).asJsonObject
        assertEquals(attempt.requestId, sent.get("client_request_id").asString)
        assertTrue(ClientRequestId.isValid(attempt.requestId))
    }

    @Test
    fun aDuplicateSubmissionAttachesToTheOriginalRun() = runTest {
        // The original run is still going when the resend arrives.
        val body = ContractFixtures.http("agent_send_duplicate_409.json").second
        body.getAsJsonObject("detail").addProperty("status", "running")
        server.enqueue(MockResponse().setResponseCode(409).setBody(body.toString()))
        replayPages = { _, _ -> if (replayCalls.size == 1) page("agent_run_events_running.json") else page("agent_run_events_running.json", "completed") }

        val (outcome, applied, recovering) = turn()

        assertEquals(1, server.requestCount) // never resent
        assertEquals(AgentTurnOutcome.Attached("00000000-0000-4000-8000-000000000001", AgentFollowResult.Finished("completed")), outcome)
        assertEquals("00000000-0000-4000-8000-000000000001", replayCalls.first().first)
        assertEquals(listOf(2, 3, 5), applied.map { it.seq })
        assertTrue(recovering)
    }

    @Test
    fun aDuplicateOfAFinishedRunJustReloads() = runTest {
        server.enqueue(json("agent_send_duplicate_409.json")) // status: failed
        val (outcome, _, _) = turn()
        assertEquals(AgentTurnOutcome.Attached("00000000-0000-4000-8000-000000000001", null), outcome)
        assertTrue(replayCalls.isEmpty())
    }

    @Test
    fun aCompleteStreamWithAnUnknownFrameEndsNormally() = runTest {
        val stream = ContractFixtures.text("agent_send_stream_completed.sse")
            .replace("event: evidence.ready", "event: workspace.preview\ndata: {\"kind\": \"chart\"}\n\nevent: evidence.ready")
        server.enqueue(MockResponse().setBody(stream))
        val (outcome, applied, recovering) = turn()
        assertEquals(AgentTurnOutcome.Streamed, outcome)
        assertTrue(applied.any { it.event == AgentStreamEvent.Ignored("workspace.preview") })
        assertTrue(applied.last().event is AgentStreamEvent.Completed)
        assertTrue(!recovering && replayCalls.isEmpty())
    }

    @Test
    fun aStreamThatDropsMidRunIsRestoredFromTheLastSeq() = runTest {
        val full = ContractFixtures.text("agent_send_stream_completed.sse")
        server.enqueue(MockResponse().setBody(full.substring(0, full.indexOf("event: tool.completed"))))
        replayPages = { _, _ -> page("agent_run_events_running.json", "completed") }

        val (outcome, applied, recovering) = turn()

        assertEquals(AgentTurnOutcome.Recovered(AgentFollowResult.Finished("completed")), outcome)
        assertTrue(recovering)
        // Live frames 1..3 were applied; the replay continued after seq 3 and applied only 5.
        assertEquals("00000000-0000-4000-8000-000000000001" to 3, replayCalls.first())
        assertEquals(listOf(1, 2, 3, 5), applied.map { it.seq })
        assertEquals(1, server.requestCount)
    }

    @Test
    fun aDropBeforeRunStartedFindsTheRunFromTheSnapshot() = runTest {
        server.enqueue(MockResponse().setBody(""))
        activeRun = "00000000-0000-4000-8000-000000000004"
        replayPages = { _, _ -> page("agent_run_events_interrupted.json") }
        val (outcome, _, _) = turn()
        assertEquals(AgentTurnOutcome.Recovered(AgentFollowResult.Finished("interrupted")), outcome)
        assertEquals("00000000-0000-4000-8000-000000000004" to 0, replayCalls.first())
    }

    @Test
    fun aRequestThatNeverGotAnAnswerIsRetryable() = runTest {
        server.enqueue(MockResponse().setSocketPolicy(SocketPolicy.DISCONNECT_AT_START))
        val (outcome, _, _) = turn()
        assertTrue((outcome as AgentTurnOutcome.Refused).failure is AgentSendFailure.Retryable)
    }

    @Test
    fun refusalsAreReportedWithoutReplay() = runTest {
        server.enqueue(json("agent_conversation_deleted_404.json"))
        assertEquals(AgentTurnOutcome.ConversationGone, turn().first)
        server.enqueue(json("agent_send_insufficient_credits_402.json"))
        assertTrue(((turn().first as AgentTurnOutcome.Refused).failure) is AgentSendFailure.Final)
        server.enqueue(json("agent_send_limit_429.json"))
        assertTrue(((turn().first as AgentTurnOutcome.Refused).failure) is AgentSendFailure.Retryable)
        assertTrue(replayCalls.isEmpty())
    }
}
