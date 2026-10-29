package ai.puregamma.android.agent

import ai.puregamma.android.data.remote.ApiErrorDetail
import ai.puregamma.android.data.remote.RetrofitApiException
import ai.puregamma.android.data.remote.ServerEvent
import ai.puregamma.android.model.AgentModel
import com.google.gson.JsonObject
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.delay
import java.io.IOException
import java.util.UUID

// Client half of the Agent session contract (docs/mobile/MOBILE_API_CONTRACT.md §8).
// Pure, or I/O passed in as functions, so every rule is unit-tested against the
// shared fixtures in docs/mobile/fixtures.

// ---- (a) idempotent send ---------------------------------------------------

object ClientRequestId {
    private val PATTERN = Regex("^[A-Za-z0-9_.:-]{8,80}$")

    /** One id per user-initiated send; a retry of that same send reuses it. */
    fun make(): String = "android-" + UUID.randomUUID().toString()
    fun isValid(value: String): Boolean = PATTERN.matches(value)
}

/** One user-initiated send and the id that makes its resends recognisable. */
data class AgentSendAttempt(
    val content: String,
    val model: String,
    val requestId: String = ClientRequestId.make(),
    /** True once the server answered with a stream: the turn exists server-side. */
    val accepted: Boolean = false,
) {
    /** What Retry sends: the same id until the server accepted it, then a new one. */
    fun forRetry(): AgentSendAttempt = if (accepted) copy(requestId = ClientRequestId.make(), accepted = false) else this
}

sealed interface AgentSendFailure {
    /** The server already has this attempt: follow its run, do not resend. */
    data class Duplicate(val runId: String, val status: String?) : AgentSendFailure
    /** The conversation was deleted (or is not the caller's). */
    data object ConversationGone : AgentSendFailure
    /** Nothing started; the same attempt may be retried with the same id. */
    data class Retryable(val error: Throwable) : AgentSendFailure
    /** Nothing started; resending cannot succeed. */
    data class Final(val error: Throwable) : AgentSendFailure

    companion object {
        private val RETRYABLE_CODES = setOf("AGENT_CONCURRENT_LIMIT_REACHED", "AGENT_GLOBAL_CAPACITY_REACHED", "AGENT_MODEL_UNAVAILABLE")

        fun classify(error: Throwable): AgentSendFailure {
            if (error is IOException) return Retryable(error)
            val api = error as? RetrofitApiException ?: return Final(error)
            val detail = api.detail ?: ApiErrorDetail(api.status, api.code, api.message)
            val runId = detail.fields["runId"]
            return when {
                detail.status == 409 && detail.code == "DUPLICATE_SUBMISSION" && !runId.isNullOrBlank() -> Duplicate(runId, detail.fields["status"])
                detail.status == 404 -> ConversationGone
                detail.code in RETRYABLE_CODES || detail.status >= 500 -> Retryable(error)
                else -> Final(error)
            }
        }
    }
}

// ---- (g) live frames, cursor, replay ---------------------------------------

sealed interface AgentStreamEvent {
    data class RunStarted(val runId: String, val messageId: String?) : AgentStreamEvent
    data class Delta(val messageId: String?, val text: String) : AgentStreamEvent
    data class ToolStarted(val tool: String) : AgentStreamEvent
    data class ToolCompleted(val tool: String, val error: String?) : AgentStreamEvent
    data class Citation(val index: Int, val provider: String, val title: String, val url: String?) : AgentStreamEvent
    data class ApprovalRequired(val tool: String) : AgentStreamEvent
    data object PlanReady : AgentStreamEvent
    data object EvidenceReady : AgentStreamEvent
    data class Completed(val messageId: String?) : AgentStreamEvent
    data class Failed(val code: String?, val message: String?) : AgentStreamEvent
    data object Canceled : AgentStreamEvent
    /** A type this build does not know: skipped, never an error. */
    data class Ignored(val name: String) : AgentStreamEvent

    val isTerminal: Boolean get() = this is Completed || this is Failed || this is Canceled
}

data class AgentFrame(val name: String, val seq: Int?, val runId: String?, val event: AgentStreamEvent) {
    companion object {
        fun parse(event: ServerEvent): AgentFrame = parse(event.name, event.data)

        fun parse(name: String, data: JsonObject): AgentFrame {
            fun text(vararg keys: String): String? = keys.firstNotNullOfOrNull { key ->
                data.get(key)?.takeIf { it.isJsonPrimitive }?.asString
            }
            val seq = data.get("seq")?.takeIf { it.isJsonPrimitive && it.asJsonPrimitive.isNumber }?.asInt
            val event = when (name) {
                "run.started" -> AgentStreamEvent.RunStarted(text("runId", "run_id", "id").orEmpty(), text("messageId"))
                "message.delta" -> AgentStreamEvent.Delta(text("messageId"), text("delta", "content").orEmpty())
                "tool.started" -> AgentStreamEvent.ToolStarted(text("tool", "name") ?: "tool")
                "tool.completed" -> AgentStreamEvent.ToolCompleted(text("tool", "name") ?: "tool", text("error"))
                "citation" -> AgentStreamEvent.Citation(
                    index = data.get("index")?.takeIf { it.isJsonPrimitive }?.asInt ?: 0,
                    provider = text("provider").orEmpty(), title = text("title").orEmpty(), url = text("url"),
                )
                "approval.required" -> AgentStreamEvent.ApprovalRequired(text("tool") ?: "tool")
                "plan.ready" -> AgentStreamEvent.PlanReady
                "evidence.ready" -> AgentStreamEvent.EvidenceReady
                "message.completed" -> AgentStreamEvent.Completed(text("messageId"))
                "run.failed" -> AgentStreamEvent.Failed(text("code"), text("message", "error"))
                "run.canceled" -> AgentStreamEvent.Canceled
                else -> AgentStreamEvent.Ignored(name)
            }
            return AgentFrame(name, seq, text("runId"), event)
        }
    }
}

/**
 * Which frames of which run have been applied. Same rules as the web
 * (`isAlreadyApplied` / `isForeignRun`): a frame at or below the cursor is a
 * re-delivery; a frame naming another run is stale.
 */
class AgentRunCursor(runId: String? = null, lastSeq: Int = 0) {
    var runId: String? = runId
        private set
    var lastSeq: Int = lastSeq
        private set

    fun attach(runId: String) {
        if (this.runId != runId) {
            this.runId = runId
            lastSeq = 0
        }
    }

    /** True when the frame is new for the active run; advances the cursor. */
    fun admit(frame: AgentFrame): Boolean {
        val started = frame.event as? AgentStreamEvent.RunStarted
        if (started != null && runId == null && started.runId.isNotEmpty()) runId = started.runId
        val active = runId
        if (frame.runId != null && !active.isNullOrEmpty() && frame.runId != active) return false
        val seq = frame.seq
        if (seq != null) {
            if (seq <= lastSeq) return false
            lastSeq = seq
        }
        return true
    }

    fun advanceTo(seq: Int) {
        lastSeq = maxOf(lastSeq, seq)
    }
}

object AgentRunStatus {
    val TERMINAL = setOf("completed", "failed", "canceled", "interrupted")
    fun isTerminal(status: String?): Boolean = status in TERMINAL
}

data class AgentRunEventsPage(
    val runId: String,
    val status: String,
    val messageId: String?,
    val conversationId: String?,
    val lastSeq: Int,
    val truncated: Boolean,
    val events: List<AgentFrame>,
) {
    companion object {
        fun parse(json: JsonObject): AgentRunEventsPage {
            fun text(key: String) = json.get(key)?.takeIf { it.isJsonPrimitive }?.asString
            val events = json.getAsJsonArray("events")?.mapNotNull { element ->
                val row = element.takeIf { it.isJsonObject }?.asJsonObject ?: return@mapNotNull null
                val seq = row.get("seq")?.asInt ?: return@mapNotNull null
                val type = row.get("type")?.asString ?: return@mapNotNull null
                val data = row.get("data")?.takeIf { it.isJsonObject }?.asJsonObject?.deepCopy() ?: JsonObject()
                data.addProperty("seq", seq)
                AgentFrame.parse(type, data)
            }.orEmpty()
            return AgentRunEventsPage(
                runId = text("runId").orEmpty(),
                status = text("status").orEmpty(),
                messageId = text("messageId"),
                conversationId = text("conversationId"),
                lastSeq = json.get("lastSeq")?.takeIf { it.isJsonPrimitive }?.asInt ?: 0,
                truncated = json.get("truncated")?.takeIf { it.isJsonPrimitive }?.asBoolean ?: false,
                events = events,
            )
        }
    }
}

sealed interface AgentFollowResult {
    /** The server recorded a final status; reload the conversation. */
    data class Finished(val status: String) : AgentFollowResult
    /** The run is not visible to this user. */
    data object NotFound : AgentFollowResult
    /** Observation stopped (deadline) — not a failure. */
    data object Detached : AgentFollowResult
}

/**
 * Follows a run through its durable event log until the server reports a
 * final status. A failed poll is not a failed run: network errors wait.
 * Cancelling the calling coroutine stops observing; it never cancels the run.
 */
class AgentRunFollower(
    private val fetch: suspend (runId: String, after: Int) -> AgentRunEventsPage,
    private val pause: suspend (Long) -> Unit = { delay(it) },
    private val pollIntervalMs: Long = 2_500,
    private val maxPolls: Int = 240,
) {
    suspend fun follow(runId: String, cursor: AgentRunCursor, apply: (AgentFrame) -> Unit): AgentFollowResult {
        cursor.attach(runId)
        var polls = 0
        while (polls < maxPolls) {
            try {
                val page = fetch(runId, cursor.lastSeq)
                page.events.filter { cursor.admit(it) }.forEach(apply)
                cursor.advanceTo(page.lastSeq)
                if (AgentRunStatus.isTerminal(page.status)) return AgentFollowResult.Finished(page.status)
                if (page.truncated) continue
            } catch (cancel: CancellationException) {
                throw cancel
            } catch (error: RetrofitApiException) {
                if (error.status == 404) return AgentFollowResult.NotFound
            } catch (_: Exception) {
                // Offline or a proxy hiccup: keep waiting.
            }
            polls += 1
            pause(pollIntervalMs)
        }
        return AgentFollowResult.Detached
    }
}

// ---- (f) model menu, (b) permission modes ----------------------------------

object AgentModelMenu {
    data class Entry(val id: String, val name: String, val selectable: Boolean, val reason: String?)

    /** Chat models only: evaluation models (e.g. jev) never write a reply. */
    fun entries(models: List<AgentModel>): List<Entry> = models
        .filter { it.category != "evaluation" }
        .map { model ->
            val selectable = model.available && model.reason == null
            Entry(model.id, model.name, selectable, if (selectable) null else (model.reason ?: "unavailable"))
        }

    /** The model to send: the current one while it stays selectable, else `default`. */
    fun resolve(current: String?, models: List<AgentModel>): String =
        entries(models).firstOrNull { it.id == current && it.selectable }?.id ?: "default"
}

enum class AgentPermissionMode(val wire: String) {
    READ_ONLY("read-only"),
    WORKSPACE_WRITE("workspace-write");

    companion object {
        fun fromWire(value: String?): AgentPermissionMode? = entries.firstOrNull { it.wire == value }

        /** Only modes the server lists AND this client knows; `full-access` is never offered. */
        fun selectable(server: List<String>): List<AgentPermissionMode> = server.mapNotNull { fromWire(it) }
    }
}

// ---- one turn: send, attach, recover ----------------------------------------

sealed interface AgentTurnOutcome {
    /** The live stream reached a terminal frame. */
    data object Streamed : AgentTurnOutcome
    /** The stream dropped; the run was followed to the server's final status. */
    data class Recovered(val result: AgentFollowResult) : AgentTurnOutcome
    /** The send was a duplicate; the original run was followed instead. */
    data class Attached(val runId: String, val result: AgentFollowResult?) : AgentTurnOutcome
    data object ConversationGone : AgentTurnOutcome
    data class Refused(val failure: AgentSendFailure) : AgentTurnOutcome
}

/**
 * Runs one turn the way the contract asks: send with the attempt's request id,
 * apply each new frame once, attach to the original run on a 409, and restore
 * a dropped stream from the event log instead of declaring it failed.
 */
class AgentTurnRunner(
    private val openStream: suspend (conversationId: String, attempt: AgentSendAttempt, onOpen: () -> Unit, onEvent: suspend (ServerEvent) -> Unit) -> Unit,
    private val follower: AgentRunFollower,
    private val activeRunId: suspend (conversationId: String) -> String?,
) {
    suspend fun run(
        conversationId: String,
        attempt: AgentSendAttempt,
        cursor: AgentRunCursor,
        onAccepted: () -> Unit,
        onRecovering: () -> Unit,
        apply: (AgentFrame) -> Unit,
    ): AgentTurnOutcome {
        var opened = false
        var ended = false
        try {
            openStream(conversationId, attempt, { opened = true; onAccepted() }) { event ->
                val frame = AgentFrame.parse(event)
                if (cursor.admit(frame)) {
                    apply(frame)
                    if (frame.event.isTerminal) ended = true
                }
            }
        } catch (cancel: CancellationException) {
            throw cancel
        } catch (error: Exception) {
            if (!opened) {
                return when (val failure = AgentSendFailure.classify(error)) {
                    is AgentSendFailure.Duplicate -> {
                        if (AgentRunStatus.isTerminal(failure.status)) {
                            AgentTurnOutcome.Attached(failure.runId, null)
                        } else {
                            onRecovering()
                            AgentTurnOutcome.Attached(failure.runId, follower.follow(failure.runId, AgentRunCursor(), apply))
                        }
                    }
                    AgentSendFailure.ConversationGone -> AgentTurnOutcome.ConversationGone
                    else -> AgentTurnOutcome.Refused(failure)
                }
            }
            // Opened, then the body died: fall through to recovery.
        }
        if (ended) return AgentTurnOutcome.Streamed
        onRecovering()
        val runId = cursor.runId ?: runCatching { activeRunId(conversationId) }.getOrNull()
            ?: return AgentTurnOutcome.Recovered(AgentFollowResult.Detached)
        return AgentTurnOutcome.Recovered(follower.follow(runId, cursor, apply))
    }
}
