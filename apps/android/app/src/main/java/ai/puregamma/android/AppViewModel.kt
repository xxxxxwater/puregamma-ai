package ai.puregamma.android

import android.app.Application
import android.net.Uri
import android.webkit.CookieManager
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import ai.puregamma.android.agent.*
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
    val liveNavRepo = LiveNavRepository(api)
    val accountRepo = AccountRepository(api)
    val mobileRepo = MobileRepository(api) {
        (mobileCapabilities as? LoadState.Ready)?.value ?: MobileCapabilities.UNAVAILABLE
    }

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

    /** 服务端能力发现结果。所有新功能入口以此为准；失败视为全部不可用。 */
    var mobileCapabilities: LoadState<MobileCapabilities> by mutableStateOf(LoadState.Idle)
        private set
    /** 待打开的受信 Web 产品路由（FCM 深链/原生入口写入，UI 消费后清空）。 */
    var pendingWebRoute: String? by mutableStateOf(null)
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
    /** Server-computed LIVE NAV; [LiveNavState.NoAccount] is an empty state, never 0. */
    var liveNav: LoadState<LiveNavState> by mutableStateOf(LoadState.Idle)
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
    /** True while a dropped stream is being restored from the server's event log. */
    var isRecovering by mutableStateOf(false)
        private set
    /** A one-off notice, e.g. the open conversation was deleted elsewhere. */
    var agentNotice: String? by mutableStateOf(null)
        private set
    /** The last send the server did not accept; Retry resends it with the same request id. */
    var pendingAttempt: AgentSendAttempt? by mutableStateOf(null)
        private set
    var permissionModes: List<AgentPermissionMode> by mutableStateOf(emptyList())
        private set
    var permission: AgentPermissionMode by mutableStateOf(AgentPermissionMode.WORKSPACE_WRITE)
        private set
    private val turnRunner = AgentTurnRunner(
        openStream = { conversationId, attempt, onOpen, onEvent ->
            val body = agentRepo.buildAgentMessageRequest(
                content = attempt.content,
                locale = language,
                dataSources = listOf("market", "rss"),
                skills = listOf("market_research", "news_research"),
                customPrompt = "",
                model = attempt.model,
                clientRequestId = attempt.requestId,
            )
            sseClient.stream("/api/agent/conversations/$conversationId/messages", body, onOpen, onEvent)
        },
        follower = AgentRunFollower(fetch = { runId, after -> agentRepo.getRunEvents(runId, after) }),
        activeRunId = { conversationId -> agentRepo.getSnapshot(conversationId).activeRunId },
    )

    init {
        PureGammaPushBridge.addMessageListener(::onPushMessage)
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
                    membershipTier = dto.membershipTier,
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
                User(dto.id, dto.email, dto.name, dto.role, dto.plan, dto.membershipTier, dto.creditBalance, dto.avatarUrl),
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
                User(dto.id, dto.email, dto.name, dto.role, dto.plan, dto.membershipTier, dto.creditBalance, dto.avatarUrl),
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
                User(dto.id, dto.email, dto.name, dto.role, dto.plan, dto.membershipTier, dto.creditBalance, dto.avatarUrl),
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
        loadMobileCapabilities()
    }

    /** 能力发现：服务端为准。404/501（契约缺失）与网络失败一律视为全部不可用。 */
    fun loadMobileCapabilities() = viewModelScope.launch {
        mobileCapabilities = LoadState.Loading
        mobileCapabilities = load { mobileRepo.getCapabilities() }
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
        // Never cached: a LIVE NAV is the server's current figure or unavailable.
        launch { liveNav = load { liveNavRepo.current() } }
    }

    fun loadAgent() = viewModelScope.launch {
        capabilities = LoadState.Loading
        conversations = LoadState.Loading
        launch {
            capabilities = load { agentRepo.getCapabilities() }
        }
        launch {
            permissionModes = runCatching { agentRepo.getPermissionModes() }.getOrDefault(emptyList())
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
            permission = AgentPermissionMode.WORKSPACE_WRITE
            messages = LoadState.Ready(emptyList())
            loadAgent()
        }.onFailure { globalError = it.message }
    }

    /**
     * Show the server's record of a conversation and reattach to the run it is
     * still producing (contract §8.6/§8.7). A deleted conversation is dropped.
     */
    fun openConversation(conversation: AgentConversation) = viewModelScope.launch {
        if (streamJob?.isActive == true && selectedConversation?.id != conversation.id) detachAgent()
        selectedConversation = conversation
        agentNotice = null
        messages = LoadState.Loading
        try {
            val snapshot = agentRepo.getSnapshot(conversation.id)
            selectedConversation = snapshot.conversation
            permission = AgentPermissionMode.fromWire(snapshot.conversation.permissionMode) ?: AgentPermissionMode.WORKSPACE_WRITE
            messages = LoadState.Ready(snapshot.messages)
            val active = snapshot.activeRunId
            if (active != null && streamJob?.isActive != true) observeRun(conversation.id, active)
        } catch (error: Exception) {
            if (!handleConversationGone(error, conversation.id)) messages = LoadState.Failed(resolveError(error, "Request failed"))
        }
    }

    fun sendAgentMessage(content: String) {
        val prompt = content.trim()
        if (prompt.isEmpty() || isStreaming) return
        val models = (capabilities as? LoadState.Ready)?.value?.models.orEmpty()
        submitAgent(AgentSendAttempt(content = prompt, model = AgentModelMenu.resolve(effectiveModel(), models)))
    }

    /** Retry the last unaccepted send with the SAME request id: a send that did arrive is attached to, never charged twice. */
    fun retryAgentMessage() {
        val attempt = pendingAttempt ?: return
        if (isStreaming) return
        submitAgent(attempt.forRetry())
    }

    private fun submitAgent(attempt: AgentSendAttempt) {
        pendingAttempt = attempt
        streamJob = viewModelScope.launch {
            if (selectedConversation == null) {
                val created = runCatching { agentRepo.createConversation() }
                    .getOrElse { globalError = it.message; return@launch }
                selectedConversation = created
            }
            val conversation = selectedConversation ?: return@launch
            val current = (messages as? LoadState.Ready)?.value.orEmpty()
            val localUserId = "local-${attempt.requestId}"
            val assistantId = "local-assistant-${attempt.requestId}"
            messages = LoadState.Ready(
                current + AgentMessage(localUserId, conversation.id, "user", attempt.content, "completed") +
                    AgentMessage(assistantId, conversation.id, "assistant", "", "streaming"),
            )
            isStreaming = true
            activeRunId = null
            globalError = null
            agentNotice = null
            var reload = true
            try {
                val outcome = turnRunner.run(
                    conversationId = conversation.id,
                    attempt = attempt,
                    cursor = AgentRunCursor(),
                    onAccepted = { pendingAttempt = attempt.copy(accepted = true) },
                    onRecovering = { isRecovering = true },
                    apply = { frame -> viewModelScope.launch(Dispatchers.Main) { applyAgentFrame(frame, assistantId) } },
                )
                when (outcome) {
                    is AgentTurnOutcome.Attached -> pendingAttempt = null
                    AgentTurnOutcome.ConversationGone -> { reload = false; handleConversationGone(RetrofitApiException(404, "Conversation not found"), conversation.id) }
                    is AgentTurnOutcome.Refused -> {
                        dropMessages(setOf(localUserId, assistantId))
                        when (val failure = outcome.failure) {
                            is AgentSendFailure.Retryable -> globalError = resolveError(failure.error, "Request failed")
                            is AgentSendFailure.Final -> {
                                pendingAttempt = null
                                globalError = resolveError(failure.error, "Request failed")
                            }
                            else -> Unit
                        }
                        reload = false
                    }
                    else -> Unit
                }
            } catch (_: CancellationException) {
                reload = false
            } finally {
                isStreaming = false
                isRecovering = false
                agentActivity = null
                activeRunId = null
            }
            if (reload) reloadConversation(conversation.id)
        }
    }

    /** Reattach to a run the server is still producing. Observation only: nothing is resent or canceled. */
    private fun observeRun(conversationId: String, runId: String) {
        streamJob = viewModelScope.launch {
            isStreaming = true
            isRecovering = true
            activeRunId = runId
            try {
                AgentRunFollower(fetch = { id, after -> agentRepo.getRunEvents(id, after) })
                    .follow(runId, AgentRunCursor()) { frame -> applyAgentFrame(frame, "") }
            } finally {
                isStreaming = false
                isRecovering = false
                agentActivity = null
                activeRunId = null
            }
            reloadConversation(conversationId)
        }
    }

    /** The server's record replaces the streamed view (contract §8.7 rule 3). */
    private suspend fun reloadConversation(conversationId: String) {
        if (selectedConversation?.id != conversationId) return
        try {
            val snapshot = agentRepo.getSnapshot(conversationId)
            messages = LoadState.Ready(snapshot.messages)
            if (snapshot.messages.lastOrNull()?.let { it.role == "assistant" && it.status == "completed" } == true) pendingAttempt = null
        } catch (error: Exception) {
            handleConversationGone(error, conversationId)
        }
        loadAgentConversationsQuietly()
    }

    private suspend fun loadAgentConversationsQuietly() {
        runCatching { agentRepo.getConversations() }.onSuccess { conversations = LoadState.Ready(it) }
    }

    /** A deleted conversation is a plain-text 404 (§8.4): drop it locally and say so. */
    private fun handleConversationGone(error: Throwable, conversationId: String): Boolean {
        val api = error as? RetrofitApiException ?: return false
        if (api.status != 404 || (api.detail?.code ?: api.code) != null) return false
        val rows = (conversations as? LoadState.Ready)?.value
        if (rows != null) conversations = LoadState.Ready(rows.filterNot { it.id == conversationId })
        if (selectedConversation?.id == conversationId) {
            detachAgent()
            selectedConversation = null
            messages = LoadState.Ready(emptyList())
            pendingAttempt = null
        }
        agentNotice = getApplication<Application>().getString(R.string.agent_conversation_deleted)
        return true
    }

    private fun dropMessages(ids: Set<String>) {
        val rows = (messages as? LoadState.Ready)?.value ?: return
        messages = LoadState.Ready(rows.filterNot { it.id in ids })
    }

    /** Explicit user stop: the only path that cancels a run. */
    fun cancelAgent() {
        val runId = activeRunId
        streamJob?.cancel()
        if (runId != null) {
            viewModelScope.launch {
                runCatching { agentRepo.cancelRun(runId) }
                    .onFailure { globalError = it.message ?: "Unable to cancel Agent run" }
                selectedConversation?.let { reloadConversation(it.id) }
            }
        }
        isStreaming = false
        isRecovering = false
        agentActivity = null
        activeRunId = null
    }

    /** Stop observing without canceling (conversation switched, sign-out). */
    fun detachAgent() {
        streamJob?.cancel()
        streamJob = null
        isStreaming = false
        isRecovering = false
        agentActivity = null
        activeRunId = null
    }

    /** Back in the foreground: re-read the server's record and reattach. */
    fun resumeAgent() {
        if (isStreaming) return
        selectedConversation?.let { openConversation(it) }
    }

    fun setPermission(mode: AgentPermissionMode) {
        if (mode == permission || isStreaming) return
        val conversation = selectedConversation ?: run { permission = mode; return }
        val previous = permission
        permission = mode
        viewModelScope.launch {
            runCatching { agentRepo.setPermission(conversation.id, mode) }
                .onSuccess { selectedConversation = it }
                .onFailure { error ->
                    permission = previous
                    if (!handleConversationGone(error, conversation.id)) globalError = resolveError(error, "Unable to change permissions")
                }
        }
    }

    fun clearAgentNotice() {
        agentNotice = null
    }

    private fun applyAgentFrame(frame: AgentFrame, assistantId: String) {
        when (val event = frame.event) {
            is AgentStreamEvent.RunStarted -> activeRunId = event.runId.ifEmpty { null }
            is AgentStreamEvent.Delta -> if (assistantId.isNotEmpty()) updateMessage(assistantId) { it.copy(content = it.content + event.text) }
            is AgentStreamEvent.ToolStarted -> agentActivity = event.tool
            is AgentStreamEvent.ToolCompleted -> agentActivity = null
            is AgentStreamEvent.ApprovalRequired -> agentActivity = event.tool
            is AgentStreamEvent.Citation -> if (assistantId.isNotEmpty()) updateMessage(assistantId) { message ->
                val source = AgentSource(index = event.index, provider = event.provider, title = event.title, url = event.url)
                message.copy(sources = (message.sources + source).distinctBy { it.index to it.url })
            }
            is AgentStreamEvent.Completed -> if (assistantId.isNotEmpty()) updateMessage(assistantId) { it.copy(status = "completed") }
            is AgentStreamEvent.Failed -> if (assistantId.isNotEmpty()) updateMessage(assistantId) { it.copy(status = "failed", error = event.message) }
            AgentStreamEvent.Canceled -> if (assistantId.isNotEmpty()) updateMessage(assistantId) { it.copy(status = "canceled") }
            AgentStreamEvent.PlanReady, AgentStreamEvent.EvidenceReady, is AgentStreamEvent.Ignored -> Unit
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

    /** 打开 Plaid Link（只读投资账户）。回调经 puregamma://plaid/callback 由 [handleDeepLink] 处理。 */
    fun connectPlaid(openBrowser: (Uri) -> Unit) = viewModelScope.launch {
        globalError = null
        runCatching { portfolioRepo.createPlaidLinkToken() }
            .onSuccess { token ->
                val plaidUrl = "https://cdn.plaid.com/link/v2/stable/link.html" +
                    "?token=$token" +
                    "&isMobileWebview=true" +
                    "&oauthRedirectUri=puregamma://plaid/callback"
                openBrowser(Uri.parse(plaidUrl))
            }
            .onFailure { globalError = resolveError(it, "Unable to open Plaid Link") }
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
        mobileCapabilities = LoadState.Idle
        pendingWebRoute = null
        // 注销时清理 WebView Cookie（含 HttpOnly 会话 Cookie），防止跨账号残留。
        runCatching { CookieManager.getInstance().removeAllCookies(null) }
    }

    private suspend fun <T> load(block: suspend () -> T): LoadState<T> =
        runCatching { block() }.fold(
            onSuccess = { LoadState.Ready(it) },
            onFailure = { LoadState.Failed(resolveError(it, "Request failed")) },
        )

    // ---- 深链与 Web 产品路由（最小化、白名单化的受信通道） ----

    /** App Link / intent 深链入口。仅处理 OAuth 回调、Plaid 回调与受信的研究路由。 */
    fun handleDeepLink(uri: Uri?) {
        if (uri == null || uri.scheme != "puregamma") return
        when {
            uri.host == "oauth" -> handleOAuth(uri)
            uri.host == "plaid" -> handlePlaidCallback(uri)
            uri.host == "research" -> {
                // puregamma://research/runs/{run_id}
                val segments = uri.pathSegments
                val runId = segments.getOrNull(1) ?: return
                if (RUN_ID_PATTERN.matches(runId)) {
                    openProductRoute("${languagePrefix()}/research/runs/$runId")
                }
            }
        }
    }

    /** Plaid Link 回调：一次性 public_token → 服务端交换并刷新组合。 */
    private fun handlePlaidCallback(uri: Uri) {
        val publicToken = uri.getQueryParameter("public_token") ?: return
        viewModelScope.launch {
            globalError = null
            runCatching { portfolioRepo.exchangePlaidToken(publicToken) }
                .onSuccess { portfolio = LoadState.Ready(it); loadPortfolio() }
                .onFailure { globalError = resolveError(it, "Plaid connection failed") }
        }
    }

    /** FCM 消息路由：研究完成通知 → 打开 Web 产品研究详情。 */
    private fun onPushMessage(data: Map<String, String>) {
        val route = data["route"] ?: return
        val runId = data["run_id"] ?: data["runId"]
        if (route == "research_run" && runId != null && RUN_ID_PATTERN.matches(runId)) {
            openProductRoute("${languagePrefix()}/research/runs/$runId")
        }
    }

    /**
     * 打开 Web 产品路由。双层门控：
     *  1) 路径白名单（杜绝任意 URL 注入）；
     *  2) 服务端 capabilities（能力未开启时拒绝，防止 WebView 覆盖层绕过 Native 门控）。
     * WebView 层另有域名白名单（PRODUCT_WEB_BASE_URL 派生）第三重约束。
     */
    fun openProductRoute(relativePath: String): Boolean {
        val path = relativePath.trim().trimStart('/')
        if (!PRODUCT_ROUTE_ALLOWLIST.matches(path)) return false
        val caps = (mobileCapabilities as? LoadState.Ready)?.value
        val sub = path.substringAfter('/')
        val gateOk = when {
            sub.startsWith("research/runs") -> caps?.serverContractAvailable == true && caps.harnessResearchEnabled
            sub.startsWith("account/memory") -> caps?.serverContractAvailable == true && caps.memoryServiceEnabled && caps.userCanManageMemory
            sub.startsWith("account/trading") || sub.startsWith("trading") -> caps?.serverContractAvailable == true && caps.autoTradingEnabled && caps.userCanViewTradingMandates
            else -> false
        }
        if (!gateOk) return false
        pendingWebRoute = BuildConfig.PRODUCT_WEB_BASE_URL.trimEnd('/') + "/" + path
        return true
    }

    fun consumePendingWebRoute(): String? {
        val route = pendingWebRoute
        pendingWebRoute = null
        return route
    }

    private fun languagePrefix(): String = if (language == "zh") "zh" else "en"

    private companion object {
        val RUN_ID_PATTERN = Regex("^[A-Za-z0-9_-]{1,64}$")
        val PRODUCT_ROUTE_ALLOWLIST = Regex("""^(en|zh)/(research/runs|account/memory|account/trading|trading)(/.*)?$""")
    }

    private fun defaultModel(): String = (capabilities as? LoadState.Ready)
        ?.value?.models?.firstOrNull { it.available }?.id ?: "default"

    private fun defaultLanguage(): String =
        if (java.util.Locale.getDefault().language.startsWith("zh")) "zh" else "en"
}
