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

    private val onUnauthorized: () -> Unit = {
        viewModelScope.launch(Dispatchers.Main) { forceSignOut() }
    }

    private var api: PureGammaApi = ApiProvider.create(tokenStore, { language }, onUnauthorized)
    private var sseClient = SseClient(
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
    var sessionError: String? by mutableStateOf(null)
        private set
    var globalError: String? by mutableStateOf(null)
        private set
    var signingIn by mutableStateOf(false)
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

    var connectingPlaid by mutableStateOf(false)
        private set
    var connectingIbkr by mutableStateOf(false)
        private set

    init {
        bootstrap()
    }

    private fun bootstrap() = viewModelScope.launch {
        val token = tokenStore.read()
        if (token == null) {
            session = SessionState.SignedOut
            return@launch
        }
        session = SessionState.Checking
        sessionError = null
        runCatching { api.getUser() }
            .onSuccess { envelope -> completeSignIn(envelope.user) }
            .onFailure { error ->
                val auth = error as? RetrofitApiException
                if (auth != null && (auth.status == 401 || auth.code == "UNAUTHORIZED")) {
                    forceSignOut()
                } else {
                    // Network or server problem: keep the token, surface a retry.
                    session = SessionState.SignedOut
                    sessionError = resolveError(error, "Unable to restore your session")
                }
            }
    }

    fun retryBootstrap() {
        if (tokenStore.read() != null) bootstrap() else {
            session = SessionState.SignedOut
            sessionError = null
        }
    }

    private fun completeSignIn(dto: UserDto) {
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

    private fun recreateClients() {
        api = ApiProvider.create(tokenStore, { language }, onUnauthorized)
        sseClient = SseClient(
            ApiProvider.createStreamOkHttpClient(tokenStore, { language }, onUnauthorized),
        )
        todayRepo.api = api
        agentRepo.api = api
        researchRepo.api = api
        portfolioRepo.api = api
        accountRepo.api = api
    }

    private fun resolveError(error: Throwable, fallback: String): String {
        val api = error as? RetrofitApiException
        if (api != null) {
            val resId = ErrorMessages.messageResFor(api.code, api.status)
            if (resId != null) return getApplication<Application>().getString(resId)
            if (api.message.isNotBlank()) return api.message
        }
        val raw = error.message
        if (!raw.isNullOrBlank() && !raw.equals("closed", ignoreCase = true)) return raw
        return fallback
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
            recreateClients()
            completeSignIn(response.user)
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
            recreateClients()
            completeSignIn(response.user)
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to create account")
        }
        signingIn = false
    }

    fun handleDeepLink(uri: Uri) = viewModelScope.launch {
        val scheme = uri.scheme
        val host = uri.host
        val path = uri.path
        if (scheme != "puregamma") return@launch
        when {
            host == "oauth" && path == "/callback" -> handleGoogleCallback(uri)
            host == "oauth" && path == "/ibkr" -> handleIbkrCallback(uri)
            host == "plaid" && path == "/callback" -> handlePlaidCallback(uri)
        }
    }

    private suspend fun handleGoogleCallback(uri: Uri) {
        signingIn = true
        globalError = null
        try {
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
            recreateClients()
            completeSignIn(response.user)
        } catch (e: Exception) {
            oauthPending.edit().clear().apply()
            globalError = resolveError(e, "Unable to complete Google sign-in")
        }
        signingIn = false
    }

    fun beginPlaidLink(openBrowser: (Uri) -> Unit) = viewModelScope.launch {
        connectingPlaid = true
        globalError = null
        try {
            val linkToken = portfolioRepo.createPlaidLinkToken()
            val linkUrl = "https://cdn.plaid.com/link/v2/stable/link.html" +
                "?token=$linkToken" +
                "&isMobileWebview=true" +
                "&oauthRedirectUri=${Uri.encode(PlaidCallbackUrl)}"
            openBrowser(Uri.parse(linkUrl))
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to start Plaid Link")
        }
        connectingPlaid = false
    }

    private suspend fun handlePlaidCallback(uri: Uri) {
        connectingPlaid = true
        globalError = null
        try {
            uri.getQueryParameter("error")?.let { error("Plaid connection failed") }
            val publicToken = uri.getQueryParameter("public_token")
                ?: uri.getQueryParameter("oauth_token")
                ?: error("Plaid callback did not contain a token")
            portfolio = LoadState.Ready(portfolioRepo.exchangePlaidToken(publicToken))
            loadPortfolio()
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to connect Plaid account")
        }
        connectingPlaid = false
    }

    fun beginIbkrOAuth(openBrowser: (Uri) -> Unit) = viewModelScope.launch {
        connectingIbkr = true
        globalError = null
        try {
            val authUrl = portfolioRepo.ibkrOAuthStart(IbkrCallbackUrl)
            openBrowser(Uri.parse(authUrl))
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to start IBKR sign-in")
        }
        connectingIbkr = false
    }

    private suspend fun handleIbkrCallback(uri: Uri) {
        connectingIbkr = true
        globalError = null
        try {
            uri.getQueryParameter("error")?.let { error("IBKR connection was canceled or failed") }
            val code = uri.getQueryParameter("code") ?: error("IBKR callback did not contain a code")
            portfolio = LoadState.Ready(portfolioRepo.ibkrOAuthComplete(code))
            loadPortfolio()
        } catch (e: Exception) {
            globalError = resolveError(e, "Unable to complete IBKR connection")
        }
        connectingIbkr = false
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
        }.onFailure { globalError = resolveError(it, "Unable to create conversation") }
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
                    .getOrElse { globalError = resolveError(it, "Unable to create conversation"); return@launch }
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
                val message = resolveError(error, "Unable to stream Agent response")
                updateMessage(assistantId) { it.copy(status = "failed", error = message) }
                globalError = message
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
                    .onFailure { globalError = resolveError(it, "Unable to cancel Agent run") }
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
            .onFailure { globalError = resolveError(it, "Unable to connect wallet") }
    }

    fun syncConnection(id: String) = viewModelScope.launch {
        runCatching { portfolioRepo.syncConnection(id) }
            .onSuccess { loadPortfolio() }
            .onFailure { globalError = resolveError(it, "Unable to sync connection") }
    }

    fun deleteConnection(id: String) = viewModelScope.launch {
        runCatching { portfolioRepo.deleteConnection(id) }
            .onSuccess { loadPortfolio() }
            .onFailure { globalError = resolveError(it, "Unable to remove connection") }
    }

    fun runAutopilotReview() = viewModelScope.launch {
        runCatching { portfolioRepo.runAutopilotReview() }
            .onSuccess { autopilot = LoadState.Ready(it); loadPortfolio() }
            .onFailure { globalError = resolveError(it, "Unable to run review") }
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
        sessionError = null
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
        sessionError = null
        markets = LoadState.Idle
        reports = LoadState.Idle
        billing = LoadState.Idle
        portfolio = LoadState.Idle
        autopilot = LoadState.Idle
        conversations = LoadState.Idle
        selectedConversation = null
        messages = LoadState.Idle
        capabilities = LoadState.Idle
        selectedModel = null
        isStreaming = false
        agentActivity = null
        activeRunId = null
        connectingPlaid = false
        connectingIbkr = false
    }

    private suspend fun <T> load(block: suspend () -> T): LoadState<T> =
        runCatching { block() }.fold(
            onSuccess = { LoadState.Ready(it) },
            onFailure = { LoadState.Failed(resolveError(it, "Request failed")) },
        )

    private fun defaultLanguage(): String =
        if (java.util.Locale.getDefault().language.startsWith("zh")) "zh" else "en"

    private companion object {
        const val PlaidCallbackUrl = "puregamma://plaid/callback"
        const val IbkrCallbackUrl = "puregamma://oauth/ibkr"
    }
}
