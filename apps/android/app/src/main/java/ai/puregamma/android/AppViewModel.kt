package ai.puregamma.android

import android.app.Application
import android.net.Uri
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.puregamma.android.data.local.SecureTokenStore
import ai.puregamma.android.data.remote.*
import ai.puregamma.android.data.remote.dto.*
import ai.puregamma.android.data.repository.*
import ai.puregamma.android.model.*
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
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

    private val oauthPending = application.getSharedPreferences("pg_oauth_pending", 0)
    private var oauthVerifier: String = ""
    private var oauthState: String = ""
    private var oauthNonce: String = ""

    private var onUnauthorized: () -> Unit = {
        viewModelScope.launch(Dispatchers.Main) { forceSignOut() }
    }

    val api: PureGammaApi = ApiProvider.create(tokenStore, { language }, onUnauthorized)
    private val sseClient = SseClient(
        ApiProvider.createStreamOkHttpClient(tokenStore, { language }, onUnauthorized),
    )

    val todayRepo = TodayRepository(api)
    val agentRepo = AgentRepository(api)
    val researchRepo = ResearchRepository(api)
    val portfolioRepo = PortfolioRepository(api)
    val accountRepo = AccountRepository(api)

    private var streamJob: Job? = null

    var session: SessionState by mutableStateOf(SessionState.Checking)
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
    var selectedModel: String? by mutableStateOf(null)
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
        runCatching { api.getUser() }
            .onSuccess { envelope ->
                val dto = envelope.user
                val user = User(
                    id = dto.id,
                    email = dto.email,
                    name = dto.name,
                    role = dto.role,
                    plan = dto.plan,
                    credits = dto.creditBalance,
                    avatarUrl = dto.avatarUrl,
                )
                session = SessionState.SignedIn(user)
                loadAll()
            }
            .onFailure { forceSignOut() }
    }

    private fun resolveError(error: Throwable, fallback: String): String {
        val api = error as? RetrofitApiException
        if (api != null) {
            val resId = ErrorMessages.messageResFor(api.code, api.status)
            if (resId != null) return getApplication<Application>().getString(resId)
        }
        return error.message?.takeIf { it.isNotBlank() } ?: fallback
    }

    fun beginGoogleSignIn(openBrowser: (Uri) -> Unit) = viewModelScope.launch {
        signingIn = true
        globalError = null
        try {
            oauthVerifier = MobileOAuth.random(48)
            oauthState = MobileOAuth.random(32)
            oauthNonce = MobileOAuth.random(32)
            oauthPending.edit()
                .putString("verifier", oauthVerifier)
                .putString("state", oauthState)
                .putString("nonce", oauthNonce)
                .commit()
            val response = api.googleOAuthStart(
                GoogleOAuthStartRequest(
                    redirectUri = MobileOAuth.CALLBACK_URL,
                    codeChallenge = MobileOAuth.challenge(oauthVerifier),
                    clientState = oauthState,
                    nonce = oauthNonce,
                ),
            )
            openBrowser(Uri.parse(response.authUrl))
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to start Google sign-in")
        }
        signingIn = false
    }

    fun emailLogin(email: String, password: String) = viewModelScope.launch {
        signingIn = true
        globalError = null
        try {
            val response = api.emailLogin(EmailLoginRequest(email.trim(), password))
            tokenStore.save(response.accessToken)
            val dto = response.user
            session = SessionState.SignedIn(
                User(dto.id, dto.email, dto.name, dto.role, dto.plan, dto.creditBalance, dto.avatarUrl),
            )
            loadAll()
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to sign in")
        }
        signingIn = false
    }

    fun emailRegister(email: String, password: String, name: String) = viewModelScope.launch {
        signingIn = true
        globalError = null
        try {
            val response = api.emailRegister(
                EmailRegisterRequest(email.trim(), password, name.trim(), language),
            )
            tokenStore.save(response.accessToken)
            val dto = response.user
            session = SessionState.SignedIn(
                User(dto.id, dto.email, dto.name, dto.role, dto.plan, dto.creditBalance, dto.avatarUrl),
            )
            loadAll()
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to create account")
        }
        signingIn = false
    }

    fun handleOAuth(uri: Uri) = viewModelScope.launch {
        signingIn = true
        globalError = null
        try {
            require(uri.scheme == "puregamma" && uri.host == "oauth" && uri.path == "/callback")
            val state = oauthPending.getString("state", null) ?: error("OAuth session expired")
            val verifier = oauthPending.getString("verifier", null) ?: error("OAuth session expired")
            val nonce = oauthPending.getString("nonce", null) ?: error("OAuth session expired")
            require(uri.getQueryParameter("state") == state) { "OAuth state verification failed" }
            uri.getQueryParameter("error")?.let { error("Google sign-in was canceled") }
            val code = uri.getQueryParameter("code") ?: error("OAuth callback did not contain a code")
            val response = api.googleOAuthExchange(
                GoogleOAuthExchangeRequest(code = code, codeVerifier = verifier, nonce = nonce),
            )
            tokenStore.save(response.accessToken)
            oauthPending.edit().clear().apply()
            val dto = response.user
            session = SessionState.SignedIn(
                User(dto.id, dto.email, dto.name, dto.role, dto.plan, dto.creditBalance, dto.avatarUrl),
            )
            loadAll()
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to complete Google sign-in")
        }
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
        launch { markets = load { todayRepo.getMarketSnapshot() } }
        launch { reports = load { todayRepo.getReports() } }
        launch { billing = load { todayRepo.getBillingSummary() } }
    }

    fun loadPortfolio() = viewModelScope.launch {
        portfolio = LoadState.Loading
        autopilot = LoadState.Loading
        launch { portfolio = load { portfolioRepo.getPortfolio() } }
        launch { autopilot = load { portfolioRepo.getAutopilot() } }
    }

    fun loadAgent() = viewModelScope.launch {
        capabilities = LoadState.Loading
        conversations = LoadState.Loading
        launch {
            capabilities = load { agentRepo.getCapabilities() }
        }
        launch {
            conversations = load { agentRepo.getConversations() }
            val rows = (conversations as? LoadState.Ready)?.value.orEmpty()
            if (selectedConversation == null && rows.isNotEmpty()) openConversation(rows.first())
            if (rows.isEmpty()) messages = LoadState.Ready(emptyList())
        }
    }

    fun createConversation() = viewModelScope.launch {
        val result = runCatching { agentRepo.createConversation() }
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
            val (_, msgs) = agentRepo.getConversation(conversation.id)
            msgs
        }
    }

    fun sendAgentMessage(content: String) {
        val prompt = content.trim()
        if (prompt.isEmpty() || isStreaming) return
        streamJob = viewModelScope.launch {
            if (selectedConversation == null) {
                val created = runCatching { agentRepo.createConversation() }
                    .getOrElse { globalError = it.message; return@launch }
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
                val chosenModel = effectiveModel()
                val body = agentRepo.buildAgentMessageRequest(
                    content = prompt,
                    locale = language,
                    dataSources = listOf("market", "rss"),
                    skills = listOf("market_research", "news_research"),
                    customPrompt = "",
                    model = chosenModel,
                )
                sseClient.stream("/api/agent/conversations/${conversation.id}/messages", body) { event ->
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
                runCatching { agentRepo.cancelRun(runId) }
                    .onFailure { globalError = it.message ?: "Unable to cancel Agent run" }
            }
        }
        isStreaming = false
        agentActivity = null
        activeRunId = null
    }

    private fun applyAgentEvent(event: ServerEvent, assistantId: String) {
        when (event.name) {
            "run.started" -> activeRunId = event.data.get("run_id")?.asString
                ?: event.data.get("runId")?.asString
                ?: event.data.get("id")?.asString
            "message.delta" -> updateMessage(assistantId) { message ->
                val delta = event.data.get("delta")?.asString
                    ?: event.data.get("content")?.asString ?: ""
                message.copy(content = message.content + delta)
            }
            "tool.started" -> agentActivity = event.data.get("tool")?.asString
                ?: event.data.get("name")?.asString ?: "Working"
            "tool.completed" -> agentActivity = null
            "citation" -> updateMessage(assistantId) { message ->
                val source = AgentSource(
                    index = event.data.get("index")?.asInt ?: 0,
                    provider = event.data.get("provider")?.asString ?: "",
                    title = event.data.get("title")?.asString ?: "",
                    url = event.data.get("url")?.asString,
                )
                message.copy(sources = (message.sources + source).distinctBy { it.index to it.url })
            }
            "message.completed" -> updateMessage(assistantId) { it.copy(status = "completed") }
            "run.failed" -> updateMessage(assistantId) {
                it.copy(
                    status = "failed",
                    error = event.data.get("message")?.asString
                        ?: event.data.get("error")?.asString,
                )
            }
        }
    }

    private fun updateMessage(id: String, transform: (AgentMessage) -> AgentMessage) {
        val rows = (messages as? LoadState.Ready)?.value ?: return
        messages = LoadState.Ready(rows.map { if (it.id == id) transform(it) else it })
    }

    fun connectHyperliquid(address: String) = viewModelScope.launch {
        globalError = null
        runCatching { portfolioRepo.connectHyperliquid(address.trim()) }
            .onSuccess { portfolio = LoadState.Ready(it); loadPortfolio() }
            .onFailure { globalError = it.message }
    }

    fun syncConnection(id: String) = viewModelScope.launch {
        runCatching { portfolioRepo.syncConnection(id) }
            .onSuccess { loadPortfolio() }
            .onFailure { globalError = it.message }
    }

    fun runAutopilotReview() = viewModelScope.launch {
        runCatching { portfolioRepo.runAutopilotReview() }
            .onSuccess { autopilot = LoadState.Ready(it); loadPortfolio() }
            .onFailure { globalError = it.message }
    }

    fun updateLanguage(value: String) {
        language = value
        preferences.edit().putString("language", value).apply()
        if (session is SessionState.SignedIn) loadAll()
    }

    fun setTheme(value: ThemeMode) {
        themeMode = value
        preferences.edit().putString("theme", value.name).apply()
    }

    fun clearError() {
        globalError = null
    }

    fun setModel(modelId: String?) {
        selectedModel = modelId
    }

    private fun effectiveModel(): String = selectedModel ?: (capabilities as? LoadState.Ready)
        ?.value?.models?.firstOrNull { it.available }?.id ?: "default"

    fun signOut() = viewModelScope.launch {
        runCatching { api.logout() }
        forceSignOut()
    }

    fun deleteAccount() = viewModelScope.launch {
        try {
            accountRepo.deleteAccount()
            forceSignOut()
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to delete account")
        }
    }

    private fun forceSignOut() {
        streamJob?.cancel()
        tokenStore.clear()
        oauthPending.edit().clear().apply()
        session = SessionState.SignedOut
        markets = LoadState.Idle
        reports = LoadState.Idle
        portfolio = LoadState.Idle
        messages = LoadState.Idle
    }

    private suspend fun <T> load(block: suspend () -> T): LoadState<T> =
        runCatching { block() }.fold(
            onSuccess = { LoadState.Ready(it) },
            onFailure = { LoadState.Failed(resolveError(it, "Request failed")) },
        )

    private fun defaultModel(): String = (capabilities as? LoadState.Ready)
        ?.value?.models?.firstOrNull { it.available }?.id ?: "default"

    private fun defaultLanguage(): String =
        if (java.util.Locale.getDefault().language.startsWith("zh")) "zh" else "en"
}
