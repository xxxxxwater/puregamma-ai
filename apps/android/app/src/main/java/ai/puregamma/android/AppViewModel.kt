package ai.puregamma.android

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.puregamma.android.core.ApiClient
import ai.puregamma.android.core.MobileOAuth
import ai.puregamma.android.core.SecureTokenStore
import ai.puregamma.android.core.ServerEvent
import ai.puregamma.android.model.*
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

sealed interface SessionState {
    data object Checking : SessionState
    data object SignedOut : SessionState
    data class SignedIn(val user: User) : SessionState
}

sealed interface LoadState<out T> {
    data object Idle : LoadState<Nothing>
    data object Loading : LoadState<Nothing>
    data class Ready<T>(val value: T) : LoadState<T>
    data class Failed(val message: String) : LoadState<Nothing>
}

enum class ThemeMode { SYSTEM, LIGHT, DARK }

class AppViewModel(application: Application) : AndroidViewModel(application) {
    private val preferences = application.getSharedPreferences("pg_settings", 0)
    private val tokenStore = SecureTokenStore(application)
    private val api = ApiClient(
        tokenStore = tokenStore,
        localeProvider = { language },
        onUnauthorized = { viewModelScope.launch(Dispatchers.Main) { forceSignOut() } },
    )
    private val oauth = MobileOAuth(application, api, tokenStore)
    private var streamJob: Job? = null

    var session: SessionState by mutableStateOf(SessionState.Checking)
        private set
    var webProductUrl: String? by mutableStateOf(null)
        private set
    var globalError: String? by mutableStateOf(null)
        private set
    var signingIn by mutableStateOf(false)
        private set
    var isRegistering by mutableStateOf(false)
        private set
    var language: String by mutableStateOf(preferences.getString("language", null) ?: defaultLanguage())
        private set
    var themeMode: ThemeMode by mutableStateOf(
        runCatching { ThemeMode.valueOf(preferences.getString("theme", ThemeMode.DARK.name)!!) }
            .getOrDefault(ThemeMode.DARK),
    )
        private set

    var markets: LoadState<List<MarketAsset>> by mutableStateOf(LoadState.Idle)
        private set
    var reports: LoadState<List<Report>> by mutableStateOf(LoadState.Idle)
        private set
    var billing: LoadState<BillingSummary> by mutableStateOf(LoadState.Idle)
        private set
    var portfolio: LoadState<Portfolio> by mutableStateOf(LoadState.Idle)
        private set
    var autopilot: LoadState<Autopilot> by mutableStateOf(LoadState.Idle)
        private set
    var conversations: LoadState<List<AgentConversation>> by mutableStateOf(LoadState.Idle)
        private set
    var selectedConversation: AgentConversation? by mutableStateOf(null)
        private set
    var messages: LoadState<List<AgentMessage>> by mutableStateOf(LoadState.Idle)
        private set
    var capabilities: LoadState<AgentCapabilities> by mutableStateOf(LoadState.Idle)
        private set
    var isStreaming by mutableStateOf(false)
        private set
    var agentActivity by mutableStateOf<String?>(null)
        private set
    private var activeRunId: String? by mutableStateOf(null)

    init {
        bootstrap()
    }

    private fun bootstrap() = viewModelScope.launch {
        val token = tokenStore.read()
        if (token == null) {
            session = SessionState.SignedOut
            return@launch
        }
        runCatching { api.get("/me").getJSONObject("user").toUser() }
            .onSuccess { user ->
                session = SessionState.SignedIn(user)
                loadAll()
                createWebProductSession()
            }
            .onFailure { forceSignOut() }
    }

    fun beginGoogleSignIn(openBrowser: (Uri) -> Unit) = viewModelScope.launch {
        signingIn = true
        globalError = null
        runCatching { oauth.beginGoogle() }
            .onSuccess(openBrowser)
            .onFailure { globalError = it.message ?: "Unable to start Google sign-in" }
        signingIn = false
    }

    fun emailLogin(email: String, password: String) = viewModelScope.launch {
        signingIn = true
        globalError = null
        val body = JSONObject().put("email", email.trim()).put("password", password)
        runCatching { api.post("/auth/mobile/email/login", body) }
            .onSuccess { response ->
                tokenStore.save(response.getString("access_token"))
                val user = response.getJSONObject("user").toUser()
                session = SessionState.SignedIn(user)
                loadAll()
                createWebProductSession()
            }
            .onFailure { globalError = it.message ?: "Unable to sign in" }
        signingIn = false
    }

    fun emailRegister(email: String, password: String, name: String) = viewModelScope.launch {
        signingIn = true
        globalError = null
        val body = JSONObject()
            .put("email", email.trim())
            .put("password", password)
            .put("name", name.trim())
            .put("locale", language)
        runCatching { api.post("/auth/mobile/email/register", body) }
            .onSuccess { response ->
                tokenStore.save(response.getString("access_token"))
                val user = response.getJSONObject("user").toUser()
                session = SessionState.SignedIn(user)
                loadAll()
                createWebProductSession()
            }
            .onFailure { globalError = it.message ?: "Unable to create account" }
        signingIn = false
    }

    fun handleOAuth(uri: Uri) = viewModelScope.launch {
        signingIn = true
        globalError = null
        runCatching { oauth.exchange(uri) }
            .onSuccess { user ->
                session = SessionState.SignedIn(user)
                loadAll()
                createWebProductSession()
            }
            .onFailure { globalError = it.message ?: "Unable to complete Google sign-in" }
        signingIn = false
    }

    fun loadAll() {
        loadToday()
        loadPortfolio()
        loadAgent()
    }

    fun loadToday() = viewModelScope.launch {
        markets = LoadState.Loading
        reports = LoadState.Loading
        billing = LoadState.Loading
        launch {
            markets = load { api.get("/market/snapshot").optJSONArray("assets").objects().map(JSONObject::toMarketAsset) }
        }
        launch {
            reports = load { api.get("/reports").optJSONArray("reports").objects().map(JSONObject::toReport) }
        }
        launch {
            billing = load {
                val value = api.get("/billing/subscription")
                BillingSummary(value.string("plan"), value.string("subscription_status"), value.optInt("credit_balance"))
            }
        }
    }

    fun loadPortfolio() = viewModelScope.launch {
        portfolio = LoadState.Loading
        autopilot = LoadState.Loading
        launch { portfolio = load { api.get("/portfolio").toPortfolio() } }
        launch { autopilot = load { api.get("/portfolio/autopilot").toAutopilot() } }
    }

    fun loadAgent() = viewModelScope.launch {
        capabilities = LoadState.Loading
        conversations = LoadState.Loading
        launch {
            capabilities = load {
                val root = api.get("/api/agent/capabilities")
                val access = root.getJSONObject("capabilities")
                val quota = root.getJSONObject("quota")
                AgentCapabilities(
                    plan = access.string("plan"),
                    dataSources = access.optJSONArray("allowed_data_sources").strings(),
                    dailyRuns = access.optInt("agent_daily_runs"),
                    concurrentRuns = access.optInt("agent_concurrent_runs"),
                    credits = quota.optInt("credit_balance"),
                    remaining = quota.optInt("remaining"),
                    models = root.optJSONArray("models").objects().map {
                        AgentModel(
                            id = it.string("id"),
                            name = it.string("display_name"),
                            provider = it.string("provider"),
                            available = it.optBoolean("available"),
                            reason = it.nullableString("reason"),
                        )
                    },
                )
            }
        }
        launch {
            conversations = load {
                api.get("/api/agent/conversations").optJSONArray("conversations").objects().map(JSONObject::toConversation)
            }
            val rows = (conversations as? LoadState.Ready)?.value.orEmpty()
            if (selectedConversation == null && rows.isNotEmpty()) openConversation(rows.first())
            if (rows.isEmpty()) messages = LoadState.Ready(emptyList())
        }
    }

    fun createConversation() = viewModelScope.launch {
        val result = runCatching {
            api.post("/api/agent/conversations", JSONObject().put("title", JSONObject.NULL))
                .getJSONObject("conversation").toConversation()
        }
        result.onSuccess {
            selectedConversation = it
            messages = LoadState.Ready(emptyList())
            loadAgent()
        }.onFailure { globalError = it.message }
    }

    fun openConversation(conversation: AgentConversation) = viewModelScope.launch {
        selectedConversation = conversation
        messages = LoadState.Loading
        messages = load {
            api.get("/api/agent/conversations/${conversation.id}")
                .optJSONArray("messages").objects().map(JSONObject::toMessage)
        }
    }

    fun sendAgentMessage(content: String) {
        val prompt = content.trim()
        if (prompt.isEmpty() || isStreaming) return
        streamJob = viewModelScope.launch {
            if (selectedConversation == null) {
                val created = runCatching {
                    api.post("/api/agent/conversations", JSONObject().put("title", JSONObject.NULL))
                        .getJSONObject("conversation").toConversation()
                }.getOrElse { globalError = it.message; return@launch }
                selectedConversation = created
            }
            val conversation = selectedConversation ?: return@launch
            val current = (messages as? LoadState.Ready)?.value.orEmpty()
            val userMessage = AgentMessage(UUID.randomUUID().toString(), conversation.id, "user", prompt, "completed")
            val assistantId = UUID.randomUUID().toString()
            val assistant = AgentMessage(assistantId, conversation.id, "assistant", "", "streaming")
            messages = LoadState.Ready(current + userMessage + assistant)
            isStreaming = true
            activeRunId = null
            globalError = null
            try {
                val request = JSONObject()
                    .put("content", prompt)
                    .put("locale", language)
                    .put("data_sources", JSONArray(listOf("market", "rss")))
                    .put("skills", JSONArray(listOf("market_research", "news_research")))
                    .put("skill_refs", JSONArray())
                    .put("custom_prompt", "")
                    .put("attachments", JSONArray())
                    .put("model", defaultModel())
                api.stream("/api/agent/conversations/${conversation.id}/messages", request) { event ->
                    withContext(Dispatchers.Main) { applyAgentEvent(event, assistantId) }
                }
            } catch (_: CancellationException) {
                agentActivity = null
            } catch (error: Exception) {
                globalError = error.message
            } finally {
                isStreaming = false
                agentActivity = null
                activeRunId = null
                openConversation(conversation)
                loadAgent()
            }
        }
    }

    fun cancelAgent() {
        val runId = activeRunId
        streamJob?.cancel()
        if (runId != null) {
            viewModelScope.launch {
                runCatching { api.post("/api/agent/runs/$runId/cancel") }
                    .onFailure { globalError = it.message ?: "Unable to cancel Agent run" }
            }
        }
        isStreaming = false
        agentActivity = null
        activeRunId = null
    }

    private fun applyAgentEvent(event: ServerEvent, assistantId: String) {
        when (event.name) {
            "run.started" -> activeRunId = event.data.optString(
                "run_id",
                event.data.optString("runId", event.data.optString("id")),
            ).takeIf(String::isNotBlank)
            "message.delta" -> updateMessage(assistantId) { message ->
                message.copy(content = message.content + event.data.optString("delta", event.data.optString("content")))
            }
            "tool.started" -> agentActivity = event.data.optString("tool", event.data.optString("name", "Working"))
            "tool.completed" -> agentActivity = null
            "citation" -> updateMessage(assistantId) { message ->
                val source = AgentSource(
                    index = event.data.optInt("index"),
                    provider = event.data.optString("provider"),
                    title = event.data.optString("title"),
                    url = event.data.nullableString("url"),
                )
                message.copy(sources = (message.sources + source).distinctBy { it.index to it.url })
            }
            "message.completed" -> updateMessage(assistantId) { it.copy(status = "completed") }
            "run.failed" -> updateMessage(assistantId) {
                it.copy(status = "failed", error = event.data.optString("message", event.data.optString("error")))
            }
        }
    }

    private fun updateMessage(id: String, transform: (AgentMessage) -> AgentMessage) {
        val rows = (messages as? LoadState.Ready)?.value ?: return
        messages = LoadState.Ready(rows.map { if (it.id == id) transform(it) else it })
    }

    fun connectHyperliquid(address: String) = viewModelScope.launch {
        globalError = null
        runCatching {
            api.post("/portfolio/hyperliquid/connect", JSONObject().put("address", address.trim()))
        }.onSuccess { loadPortfolio() }.onFailure { globalError = it.message }
    }

    fun syncConnection(id: String) = viewModelScope.launch {
        runCatching { api.post("/portfolio/accounts/$id/sync") }
            .onSuccess { loadPortfolio() }
            .onFailure { globalError = it.message }
    }

    fun runAutopilotReview() = viewModelScope.launch {
        runCatching { api.post("/portfolio/autopilot/run") }
            .onSuccess { loadPortfolio() }
            .onFailure { globalError = it.message }
    }

    fun updateLanguage(value: String) {
        language = value
        preferences.edit().putString("language", value).apply()
        if (session is SessionState.SignedIn) {
            loadAll()
            createWebProductSession()
        }
    }

    fun setTheme(value: ThemeMode) {
        themeMode = value
        preferences.edit().putString("theme", value.name).apply()
    }

    fun clearError() {
        globalError = null
    }

    fun signOut() = viewModelScope.launch {
        runCatching { api.post("/auth/logout") }
        forceSignOut()
    }

    private fun forceSignOut() {
        streamJob?.cancel()
        tokenStore.clear()
        oauth.clearPending()
        webProductUrl = null
        session = SessionState.SignedOut
        markets = LoadState.Idle
        reports = LoadState.Idle
        portfolio = LoadState.Idle
        messages = LoadState.Idle
    }

    private suspend fun <T> load(block: suspend () -> T): LoadState<T> =
        runCatching { block() }.fold(
            onSuccess = { LoadState.Ready(it) },
            onFailure = { LoadState.Failed(it.message ?: "Request failed") },
        )

    private fun createWebProductSession() = viewModelScope.launch {
        webProductUrl = null
        runCatching {
            val response = api.post(
                "/auth/mobile/web-session",
                JSONObject().put("locale", language),
            )
            "${BuildConfig.API_BASE_URL.trimEnd('/')}${response.getString("handoff_path")}"
        }.onSuccess { url ->
            webProductUrl = url
        }.onFailure { error ->
            globalError = error.message ?: "Unable to start the PureGamma web session"
        }
    }

    private fun defaultModel(): String = (capabilities as? LoadState.Ready)
        ?.value?.models?.firstOrNull { it.available }?.id ?: "default"

    private fun defaultLanguage(): String =
        if (java.util.Locale.getDefault().language.startsWith("zh")) "zh" else "en"
}
