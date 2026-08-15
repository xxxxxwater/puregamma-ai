package ai.puregamma.android.ui

import android.content.res.Configuration
import android.net.Uri
import android.app.Activity
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.Article
import androidx.compose.material.icons.automirrored.filled.ExitToApp
import androidx.compose.material.icons.automirrored.filled.Login
import androidx.compose.material.icons.automirrored.filled.Send
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.view.WindowCompat
import ai.puregamma.android.*
import ai.puregamma.android.R
import ai.puregamma.android.model.*
import ai.puregamma.android.ui.component.NavHistoryChart
import java.text.NumberFormat
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Currency
import java.util.Locale

private val Accent = Color(0xFFD4D4D8)
private val Positive = Color(0xFFD9F99D)
private val Negative = Color(0xFFFCA5A5)
private val Warning = Color(0xFFFDE68A)
private val BrandGold = Color(0xFFD6B35A)

private enum class AppTab(val label: Int, val icon: ImageVector) {
    TODAY(R.string.today, Icons.Default.Today),
    AGENT(R.string.agent, Icons.Default.AutoAwesome),
    RESEARCH(R.string.research, Icons.AutoMirrored.Filled.Article),
    PORTFOLIO(R.string.portfolio, Icons.Default.AccountBalanceWallet),
    ACCOUNT(R.string.account, Icons.Default.Person),
}

@Composable
fun PureGammaApp(model: AppViewModel, openBrowser: (Uri) -> Unit) {
    val systemDark = androidx.compose.foundation.isSystemInDarkTheme()
    val dark = when (model.themeMode) {
        ThemeMode.SYSTEM -> systemDark
        ThemeMode.LIGHT -> false
        ThemeMode.DARK -> true
    }
    val base = if (dark) darkColorScheme(
        // DeepSeek console grey scale (matches web globals.css):
        // background #101216, surface #191c22, surfaceVariant #212123,
        // text #F5F6F8 / #A2A4A6, borders at 6% / 12% white.
        primary = Color(0xFFF5F6F8),
        onPrimary = Color(0xFF101216),
        secondary = Color(0xFFD4D4D8),
        background = Color(0xFF101216),
        surface = Color(0xFF191C22),
        surfaceVariant = Color(0xFF212123),
        onSurface = Color(0xFFF5F6F8),
        onSurfaceVariant = Color(0xFFA2A4A6),
        outline = Color(0x0FFFFFFF),
        outlineVariant = Color(0x1FFFFFFF),
    ) else lightColorScheme(
        primary = Color(0xFF171717),
        onPrimary = Color.White,
        secondary = Color(0xFF3F3F46),
        background = Color(0xFFF6F7F8),
        surface = Color.White,
        surfaceVariant = Color(0xFFF0F1F2),
        onSurface = Color(0xFF171717),
        onSurfaceVariant = Color(0xFF525252),
        outline = Color(0x1F000000),
        outlineVariant = Color(0x1F000000),
    )
    val view = androidx.compose.ui.platform.LocalView.current
    SideEffect {
        val window = (view.context as? Activity)?.window ?: return@SideEffect
        window.statusBarColor = if (dark) android.graphics.Color.rgb(3, 3, 3) else android.graphics.Color.rgb(246, 247, 248)
        window.navigationBarColor = window.statusBarColor
        WindowCompat.getInsetsController(window, view).apply {
            isAppearanceLightStatusBars = !dark
            isAppearanceLightNavigationBars = !dark
        }
    }
    LocalizedResources(model.language) {
        MaterialTheme(colorScheme = base, typography = pgTypography()) {
            Surface(Modifier.fillMaxSize()) {
                when (model.session) {
                    SessionState.Checking -> LoadingScreen()
                    SessionState.SignedOut -> LoginScreen(model, openBrowser)
                    is SessionState.SignedIn -> SignedInApp(model)
                }
            }
        }
    }
}

@Composable
private fun LocalizedResources(language: String, content: @Composable () -> Unit) {
    val context = LocalContext.current
    val current = LocalConfiguration.current
    val localized = remember(language, current) {
        Configuration(current).apply {
            setLocale(if (language == "zh") Locale.SIMPLIFIED_CHINESE else Locale.ENGLISH)
        }
    }
    CompositionLocalProvider(
        androidx.compose.ui.platform.LocalContext provides context.createConfigurationContext(localized),
        androidx.compose.ui.platform.LocalConfiguration provides localized,
        content = content,
    )
}

@Composable
private fun pgTypography(): Typography {
    val base = Typography()
    return base.copy(
        headlineLarge = base.headlineLarge.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.sp),
        headlineSmall = base.headlineSmall.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.sp),
        titleMedium = base.titleMedium.copy(fontWeight = FontWeight.SemiBold, letterSpacing = 0.sp),
        labelSmall = base.labelSmall.copy(fontFamily = FontFamily.Monospace, letterSpacing = 0.sp),
    )
}

@Composable
private fun LoadingScreen() {
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        CircularProgressIndicator()
    }
}

@Composable
private fun LoginScreen(model: AppViewModel, openBrowser: (Uri) -> Unit) {
    var email by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var name by remember { mutableStateOf("") }
    var showRegister by remember { mutableStateOf(false) }

    Box(Modifier.fillMaxSize().padding(horizontal = 24.dp).verticalScroll(rememberScrollState())) {
        Column(
            Modifier.align(Alignment.Center).widthIn(max = 420.dp).fillMaxWidth(),
            horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(
                    modifier = Modifier.size(32.dp).border(1.dp, BrandGold).padding(3.dp),
                    contentAlignment = Alignment.Center,
                ) {
                    Image(
                        painter = painterResource(R.drawable.pg_logo),
                        contentDescription = stringResource(R.string.app_name),
                        modifier = Modifier.size(24.dp),
                    )
                }
                Text("PureGamma AI", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            }
            Spacer(Modifier.height(32.dp))
            Text(stringResource(R.string.welcome_back), style = MaterialTheme.typography.headlineSmall)
            Spacer(Modifier.height(8.dp))
            Text(stringResource(R.string.sign_in_console), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.height(24.dp))
            Column(
                Modifier.fillMaxWidth().border(1.dp, MaterialTheme.colorScheme.outline).background(MaterialTheme.colorScheme.surface).padding(20.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                model.globalError?.let { InlineError(it, model::clearError) }

                OutlinedTextField(
                    value = email,
                    onValueChange = { email = it },
                    label = { Text(stringResource(R.string.email)) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Email, imeAction = ImeAction.Next),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = MaterialTheme.colorScheme.outline,
                        unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant,
                    ),
                )

                OutlinedTextField(
                    value = password,
                    onValueChange = { password = it },
                    label = { Text(stringResource(R.string.password)) },
                    singleLine = true,
                    visualTransformation = PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password, imeAction = if (showRegister) ImeAction.Next else ImeAction.Done),
                    colors = OutlinedTextFieldDefaults.colors(
                        focusedBorderColor = MaterialTheme.colorScheme.outline,
                        unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant,
                    ),
                )

                if (showRegister) {
                    OutlinedTextField(
                        value = name,
                        onValueChange = { name = it },
                        label = { Text(stringResource(R.string.name_optional)) },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth(),
                        keyboardOptions = KeyboardOptions(imeAction = ImeAction.Done),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = MaterialTheme.colorScheme.outline,
                            unfocusedBorderColor = MaterialTheme.colorScheme.outlineVariant,
                        ),
                    )
                }

                Button(
                    onClick = {
                        if (showRegister) model.emailRegister(email, password, name)
                        else model.emailLogin(email, password)
                    },
                    enabled = !model.signingIn && email.isNotBlank() && password.isNotBlank(),
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = BrandGold, contentColor = Color(0xFF101216)),
                ) {
                    if (model.signingIn) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = Color(0xFF101216))
                    else Icon(Icons.AutoMirrored.Filled.Login, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(if (showRegister) stringResource(R.string.sign_up) else stringResource(R.string.sign_in_email), fontWeight = FontWeight.SemiBold)
                }

                HorizontalDivider()

                Button(
                    onClick = { model.beginGoogleSignIn(openBrowser) },
                    enabled = !model.signingIn,
                    modifier = Modifier.fillMaxWidth().height(48.dp),
                    shape = RoundedCornerShape(12.dp),
                    colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.surfaceVariant, contentColor = MaterialTheme.colorScheme.onSurface),
                    border = BorderStroke(1.dp, MaterialTheme.colorScheme.outline),
                ) {
                    if (model.signingIn) CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp)
                    else Icon(Icons.AutoMirrored.Filled.Login, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(Modifier.width(10.dp))
                    Text(stringResource(R.string.sign_in_google), fontWeight = FontWeight.SemiBold)
                }
            }

            Spacer(Modifier.height(14.dp))

            TextButton(
                onClick = {
                    showRegister = !showRegister
                    model.clearError()
                },
                enabled = !model.signingIn,
            ) {
                Text(
                    if (showRegister) stringResource(R.string.have_account) else stringResource(R.string.no_account),
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(4.dp))
            Text(stringResource(R.string.login_legal), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable
private fun SignedInApp(model: AppViewModel) {
    var selected by rememberSaveable { mutableStateOf(AppTab.TODAY) }
    var webOverlayUrl by rememberSaveable { mutableStateOf<String?>(null) }
    val snackbar = remember { SnackbarHostState() }
    val error = model.globalError
    LaunchedEffect(error) {
        error?.let {
            snackbar.showSnackbar(it)
            model.clearError()
        }
    }
    // 深链/推送写入的受信 Web 产品路由：消费后打开 WebView 覆盖层。
    LaunchedEffect(model.pendingWebRoute) {
        model.pendingWebRoute?.let { route ->
            webOverlayUrl = model.consumePendingWebRoute()
        }
    }
    Scaffold(
        snackbarHost = { SnackbarHost(snackbar) },
        bottomBar = {
            NavigationBar(tonalElevation = 0.dp) {
                AppTab.entries.forEach { tab ->
                    NavigationBarItem(
                        selected = selected == tab,
                        onClick = { selected = tab },
                        icon = { Icon(tab.icon, contentDescription = stringResource(tab.label)) },
                        label = { Text(stringResource(tab.label), maxLines = 1) },
                    )
                }
            }
        },
    ) { padding ->
        Box(Modifier.padding(padding).fillMaxSize()) {
            when (selected) {
                AppTab.TODAY -> TodayScreen(model)
                AppTab.AGENT -> AgentScreen(model)
                AppTab.RESEARCH -> ResearchScreen(model)
                AppTab.PORTFOLIO -> PortfolioScreen(model)
                AppTab.ACCOUNT -> AccountScreen(model)
            }
            webOverlayUrl?.let { url ->
                ProductWebOverlay(
                    entryUrl = url,
                    onClose = { webOverlayUrl = null },
                    onSignOut = {
                        webOverlayUrl = null
                        model.signOut()
                    },
                )
            }
        }
    }
}

/**
 * 受信 Web 产品覆盖层：只加载 PRODUCT_WEB_BASE_URL 下的白名单路由，
 * WebView 内部再按域名白名单二次校验（WebProductScreen）。
 */
@Composable
private fun ProductWebOverlay(entryUrl: String, onClose: () -> Unit, onSignOut: () -> Unit) {
    Column(Modifier.fillMaxSize().background(Color(0xFF101216))) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 8.dp, vertical = 6.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            IconButton(onClick = onClose) {
                Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = stringResource(R.string.web_overlay_close))
            }
            Text("PureGamma", style = MaterialTheme.typography.titleSmall)
        }
        WebProductScreen(entryUrl = entryUrl, onSignOut = onSignOut)
    }
}

@Composable
private fun ScreenHeader(title: String, subtitle: String? = null, refresh: (() -> Unit)? = null) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        Column(Modifier.weight(1f)) {
            Text(title, style = MaterialTheme.typography.headlineSmall)
            subtitle?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        refresh?.let {
            IconButton(onClick = it) { Icon(Icons.Default.Refresh, contentDescription = stringResource(R.string.refresh)) }
        }
    }
    HorizontalDivider()
}

@Composable
private fun TodayScreen(model: AppViewModel) {
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item { ScreenHeader(stringResource(R.string.today), "DECISION SUPPORT / UTC INPUT", model::loadToday) }
        item { BillingStrip(model.billing) }
        item { SectionTitle("01", stringResource(R.string.markets), "REAL DATA") }
        when (val state = model.markets) {
            LoadState.Idle, LoadState.Loading -> item { LoadingBlock() }
            is LoadState.Failed -> item { ErrorBlock(state.message, model::loadToday) }
            is LoadState.Ready -> if (state.value.isEmpty()) item { EmptyBlock() } else items(state.value, key = { it.symbol }) { MarketRow(it) }
        }
        item { SectionTitle("02", stringResource(R.string.latest_research), null) }
        when (val state = model.reports) {
            LoadState.Idle, LoadState.Loading -> item { LoadingBlock() }
            is LoadState.Failed -> item { ErrorBlock(state.message, model::loadToday) }
            is LoadState.Ready -> if (state.value.isEmpty()) item { EmptyBlock() } else items(state.value.take(4), key = { it.id }) { ReportRow(it) }
        }
        item { Disclosure() }
    }
}

@Composable
private fun BillingStrip(state: LoadState<BillingSummary>) {
    when (state) {
        LoadState.Idle, LoadState.Loading -> LoadingBlock()
        is LoadState.Failed -> ErrorBlock(state.message, null)
        is LoadState.Ready -> Row(
            Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 14.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            Metric(stringResource(R.string.plan), state.value.plan, Modifier.weight(1f))
            Metric(stringResource(R.string.credits), state.value.credits.toString(), Modifier.weight(1f))
            Metric(stringResource(R.string.status), state.value.status.uppercase(), Modifier.weight(1f))
        }
    }
}

@Composable
private fun Metric(label: String, value: String, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(label.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(value, style = MaterialTheme.typography.titleMedium, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
private fun SectionTitle(index: String, title: String, trailing: String?) {
    Row(Modifier.fillMaxWidth().padding(start = 16.dp, end = 16.dp, top = 24.dp, bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(index, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
        Spacer(Modifier.width(10.dp))
        Text(title, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
        trailing?.let { Text(it, style = MaterialTheme.typography.labelSmall, color = Positive) }
    }
    HorizontalDivider(Modifier.padding(horizontal = 16.dp))
}

@Composable
private fun MarketRow(asset: MarketAsset) {
    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 12.dp), verticalAlignment = Alignment.CenterVertically) {
        AssetIcon(asset)
        Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1.25f)) {
            Text(asset.symbol, fontWeight = FontWeight.SemiBold)
            Text(asset.source, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Text(money(asset.price), fontFamily = FontFamily.Monospace, modifier = Modifier.weight(1f))
        Text(
            percent(asset.change24h),
            fontFamily = FontFamily.Monospace,
            color = when { (asset.change24h ?: 0.0) > 0 -> Positive; (asset.change24h ?: 0.0) < 0 -> Negative; else -> MaterialTheme.colorScheme.onSurfaceVariant },
            modifier = Modifier.weight(.8f),
        )
        Box(Modifier.size(7.dp).clip(RoundedCornerShape(50)).background(if (asset.realtime) Positive else Warning))
    }
    HorizontalDivider(Modifier.padding(horizontal = 16.dp), color = MaterialTheme.colorScheme.outlineVariant.copy(alpha = .55f))
}

/** Hyperliquid asset icon (bundled PNG) with a letter-badge fallback. */
@Composable
private fun AssetIcon(asset: MarketAsset) {
    val coin = asset.symbol.uppercase().replace("-USDC", "").replace("USDC", "").replace("DLY", "").trim()
    val icon = when (coin) {
        "BTC" -> R.drawable.ic_coin_btc
        "ETH" -> R.drawable.ic_coin_eth
        "HYPE" -> R.drawable.ic_coin_hype
        "ZEC" -> R.drawable.ic_coin_zec
        "SOL" -> R.drawable.ic_coin_sol
        "CASHCAT" -> R.drawable.ic_coin_cashcat
        "ONDO" -> R.drawable.ic_coin_ondo
        else -> null
    }
    if (icon != null) {
        Image(
            painterResource(icon),
            contentDescription = coin,
            modifier = Modifier.size(22.dp).clip(CircleShape),
        )
    } else {
        Box(
            Modifier.size(22.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceVariant),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                coin.take(1),
                fontSize = 10.sp,
                fontWeight = FontWeight.Bold,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ReportRow(report: Report) {
    var expanded by remember(report.id) { mutableStateOf(false) }
    Column(
        Modifier.fillMaxWidth().clickable { expanded = !expanded }.padding(horizontal = 16.dp, vertical = 14.dp),
        verticalArrangement = Arrangement.spacedBy(7.dp),
    ) {
        Row(verticalAlignment = Alignment.Top) {
            Column(Modifier.weight(1f)) {
                Text(report.type.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                Text(report.title, style = MaterialTheme.typography.titleMedium)
                Text(date(report.createdAt), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Icon(if (expanded) Icons.Default.ExpandLess else Icons.Default.ExpandMore, contentDescription = null)
        }
        if (expanded) MarkdownBody(report.markdown)
    }
    HorizontalDivider(Modifier.padding(horizontal = 16.dp))
}

@Composable
private fun AgentScreen(model: AppViewModel) {
    var prompt by remember { mutableStateOf("") }
    var showContext by remember { mutableStateOf(false) }
    val rows = (model.messages as? LoadState.Ready)?.value.orEmpty()
    val listState = rememberLazyListState()
    val caps = model.capabilities as? LoadState.Ready
    LaunchedEffect(rows.size, rows.lastOrNull()?.content) {
        if (rows.isNotEmpty()) listState.scrollToItem(rows.lastIndex)
    }
    Column(Modifier.fillMaxSize()) {
        ScreenHeader(model.selectedConversation?.title ?: stringResource(R.string.agent), if (model.isStreaming) "RUNNING" else "READY", model::loadAgent)
        ConversationBar(model)
        if (showContext && caps != null) {
            AgentContextPanel(caps.value, model.selectedModel, { model.setModel(it) }, onDismiss = { showContext = false })
        }
        when (val state = model.messages) {
            LoadState.Idle, LoadState.Loading -> LoadingBlock(Modifier.weight(1f))
            is LoadState.Failed -> ErrorBlock(state.message, model::loadAgent, Modifier.weight(1f))
            is LoadState.Ready -> if (state.value.isEmpty()) {
                Box(Modifier.weight(1f).fillMaxWidth(), contentAlignment = Alignment.Center) {
                    Text(stringResource(R.string.ask_agent), color = MaterialTheme.colorScheme.onSurfaceVariant)
                }
            } else LazyColumn(
                state = listState,
                modifier = Modifier.weight(1f).fillMaxWidth(),
                contentPadding = PaddingValues(16.dp),
                verticalArrangement = Arrangement.spacedBy(18.dp),
            ) {
                items(state.value, key = { it.id }) { AgentMessageRow(it) }
                model.agentActivity?.let { activity ->
                    item { Text("RUNNING / $activity", style = MaterialTheme.typography.labelSmall, color = Warning) }
                }
            }
        }
        HorizontalDivider()
        Row(Modifier.fillMaxWidth().padding(12.dp), verticalAlignment = Alignment.Bottom) {
            IconButton(onClick = { showContext = !showContext }) {
                Icon(Icons.Default.Tune, contentDescription = "Context", tint = if (showContext) BrandGold else MaterialTheme.colorScheme.onSurfaceVariant)
            }
            OutlinedTextField(
                value = prompt,
                onValueChange = { prompt = it },
                modifier = Modifier.weight(1f),
                placeholder = { Text(stringResource(R.string.ask_agent)) },
                minLines = 1,
                maxLines = 5,
                shape = RoundedCornerShape(6.dp),
                keyboardOptions = KeyboardOptions(imeAction = ImeAction.Send),
                keyboardActions = KeyboardActions(onSend = {
                    if (prompt.isNotBlank() && !model.isStreaming) {
                        model.sendAgentMessage(prompt)
                        prompt = ""
                    }
                }),
            )
            Spacer(Modifier.width(8.dp))
            FilledIconButton(
                onClick = {
                    if (model.isStreaming) model.cancelAgent() else {
                        model.sendAgentMessage(prompt)
                        prompt = ""
                    }
                },
                enabled = model.isStreaming || prompt.isNotBlank(),
                shape = RoundedCornerShape(6.dp),
                modifier = Modifier.size(48.dp),
            ) {
                Icon(if (model.isStreaming) Icons.Default.Stop else Icons.AutoMirrored.Filled.Send, contentDescription = stringResource(if (model.isStreaming) R.string.stop else R.string.send))
            }
        }
    }
}

@Composable
private fun AgentContextPanel(caps: AgentCapabilities, selectedModel: String?, setModel: (String) -> Unit, onDismiss: () -> Unit) {
    Column(
        Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(6.dp)).padding(12.dp),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Text("Context", style = MaterialTheme.typography.labelSmall, color = BrandGold)
            Text("${caps.credits} CREDITS / ${caps.remaining} REMAINING", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            IconButton(onClick = onDismiss, modifier = Modifier.size(24.dp)) {
                Icon(Icons.Default.Close, contentDescription = "Close", modifier = Modifier.size(16.dp))
            }
        }
        Text("Models", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            caps.models.take(4).forEach { md ->
                FilterChip(
                    selected = md.id == (selectedModel ?: caps.models.firstOrNull { it.available }?.id),
                    onClick = { if (md.available) setModel(md.id) },
                    label = { Text(md.name, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                    enabled = md.available,
                )
            }
        }
        Text(caps.dataSources.joinToString(" / "), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun ConversationBar(model: AppViewModel) {
    val conversations = (model.conversations as? LoadState.Ready)?.value.orEmpty()
    Row(Modifier.fillMaxWidth().padding(horizontal = 12.dp, vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        IconButton(onClick = model::createConversation) {
            Icon(Icons.Default.AddComment, contentDescription = stringResource(R.string.new_conversation))
        }
        LazyRow(Modifier.weight(1f), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            items(conversations, key = { it.id }) { row ->
                FilterChip(
                    selected = model.selectedConversation?.id == row.id,
                    onClick = { model.openConversation(row) },
                    label = { Text(row.title, maxLines = 1, overflow = TextOverflow.Ellipsis) },
                )
            }
        }
        val access = model.capabilities as? LoadState.Ready
        access?.let { Text(it.value.credits.toString(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary) }
    }
    HorizontalDivider()
}

@Composable
private fun AgentMessageRow(message: AgentMessage) {
    val user = message.role == "user"
    Column(
        Modifier.fillMaxWidth().then(
            if (user) Modifier.background(MaterialTheme.colorScheme.surfaceVariant, RoundedCornerShape(6.dp)).padding(12.dp)
            else Modifier,
        ),
        verticalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        Text(if (user) "YOU" else "PG / AGENT", style = MaterialTheme.typography.labelSmall, color = if (user) MaterialTheme.colorScheme.onSurfaceVariant else MaterialTheme.colorScheme.primary)
        Text(message.content.ifEmpty { "..." })
        message.error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Negative) }
        if (message.sources.isNotEmpty()) {
            HorizontalDivider()
            message.sources.sortedBy { it.index }.forEach {
                Text("[${it.index}] ${it.title} / ${it.provider}", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.secondary)
            }
        }
    }
}

@Composable
private fun ResearchScreen(model: AppViewModel) {
    var typeFilter by remember { mutableStateOf<String?>(null) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item { ScreenHeader(stringResource(R.string.research), "REPORTS / HARNESS / SOURCES", model::loadToday) }
        item { HarnessResearchBlock(model) }
        when (val state = model.reports) {
            LoadState.Idle, LoadState.Loading -> item { LoadingBlock() }
            is LoadState.Failed -> item { ErrorBlock(state.message, model::loadToday) }
            is LoadState.Ready -> {
                val types = state.value.map { it.type }.distinct().sorted()
                val filtered = if (typeFilter == null) state.value else state.value.filter { it.type == typeFilter }
                if (types.size > 1) {
                    item {
                        LazyRow(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            item {
                                FilterChip(
                                    selected = typeFilter == null,
                                    onClick = { typeFilter = null },
                                    label = { Text("ALL") },
                                )
                            }
                            items(types) { type ->
                                FilterChip(
                                    selected = typeFilter == type,
                                    onClick = { typeFilter = if (typeFilter == type) null else type },
                                    label = { Text(type.uppercase()) },
                                )
                            }
                        }
                    }
                }
                if (filtered.isEmpty()) item { EmptyBlock() }
                else items(filtered, key = { it.id }) { ReportRow(it) }
            }
        }
        item { Disclosure() }
    }
}

/**
 * Harness 研究入口：能力完全由服务端决定。
 * 可用 → 打开受信 Web 产品路由；不可用 → 灰色不可操作状态，绝不展示假数据。
 */
@Composable
private fun HarnessResearchBlock(model: AppViewModel) {
    val capabilities = (model.mobileCapabilities as? LoadState.Ready)?.value
    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.Science, contentDescription = null, tint = if (capabilities?.harnessResearchEnabled == true) Positive else MaterialTheme.colorScheme.onSurfaceVariant)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(stringResource(R.string.harness_research), fontWeight = FontWeight.SemiBold)
                Text(
                    when {
                        capabilities == null || !capabilities.serverContractAvailable -> stringResource(R.string.feature_not_available_yet)
                        !capabilities.harnessResearchEnabled -> stringResource(R.string.feature_disabled_for_account)
                        else -> capabilities.maintenanceMessage ?: stringResource(R.string.harness_research_subtitle)
                    },
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            if (capabilities?.serverContractAvailable == true && capabilities.harnessResearchEnabled && capabilities.userCanStartResearch) {
                OutlinedButton(
                    onClick = { model.openProductRoute(if (model.language == "zh") "zh/research/runs" else "en/research/runs") },
                    shape = RoundedCornerShape(6.dp),
                ) {
                    Icon(Icons.Default.OpenInNew, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(Modifier.width(6.dp))
                    Text(stringResource(R.string.open_in_web))
                }
            }
        }
    }
}

@Composable
private fun PortfolioScreen(model: AppViewModel) {
    var wallet by remember { mutableStateOf("") }
    var navPoints by remember { mutableStateOf<List<NavPoint>>(emptyList()) }
    LazyColumn(Modifier.fillMaxSize(), contentPadding = PaddingValues(bottom = 24.dp)) {
        item { ScreenHeader(stringResource(R.string.portfolio), "READ-ONLY / NO EXECUTION", model::loadPortfolio) }
        when (val state = model.portfolio) {
            LoadState.Idle, LoadState.Loading -> item { LoadingBlock() }
            is LoadState.Failed -> item { ErrorBlock(state.message, model::loadPortfolio) }
            is LoadState.Ready -> {
                if (state.value.navHistory.isNotEmpty()) {
                    item {
                        LaunchedEffect(state.value) { navPoints = state.value.navHistory }
                        NavHistoryChart(
                            points = navPoints,
                            modifier = Modifier.padding(vertical = 12.dp),
                        )
                    }
                    item { HorizontalDivider(Modifier.padding(horizontal = 16.dp)) }
                }
                item {
                    Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.spacedBy(16.dp)) {
                        Metric(stringResource(R.string.nav), money(state.value.nav), Modifier.weight(1f))
                        Metric(stringResource(R.string.available_cash), money(state.value.availableCash), Modifier.weight(1f))
                    }
                }
                item { SectionTitle("01", stringResource(R.string.connections), if (state.value.stale) "STALE" else "READ ONLY") }
                if (state.value.connections.isEmpty()) item { EmptyBlock() }
                else items(state.value.connections, key = { it.id }) { connection ->
                    Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Column(Modifier.weight(1f)) {
                            Text(connection.name, fontWeight = FontWeight.SemiBold)
                            Text("${connection.provider} / ${connection.status}", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                            connection.error?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Negative) }
                        }
                        IconButton(onClick = { model.syncConnection(connection.id) }) { Icon(Icons.Default.Sync, contentDescription = stringResource(R.string.refresh)) }
                    }
                    HorizontalDivider(Modifier.padding(horizontal = 16.dp))
                }
                item {
                    Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                        Text("Hyperliquid", style = MaterialTheme.typography.titleMedium)
                        OutlinedTextField(
                            value = wallet,
                            onValueChange = { wallet = it },
                            label = { Text("0x wallet address") },
                            singleLine = true,
                            modifier = Modifier.fillMaxWidth(),
                        )
                        Button(onClick = { model.connectHyperliquid(wallet) }, enabled = wallet.trim().length == 42, shape = RoundedCornerShape(6.dp)) {
                            Icon(Icons.Default.Link, contentDescription = null)
                            Spacer(Modifier.width(8.dp))
                            Text("Connect read-only wallet")
                        }
                    }
                }
            }
        }
        item { SectionTitle("02", stringResource(R.string.autopilot), "RESEARCH ONLY") }
        item { AutopilotBlock(model.autopilot, model::runAutopilotReview) }
        item { Disclosure(stringResource(R.string.research_only)) }
    }
}

@Composable
private fun AutopilotBlock(state: LoadState<Autopilot>, run: () -> Unit) {
    when (state) {
        LoadState.Idle, LoadState.Loading -> LoadingBlock()
        is LoadState.Failed -> ErrorBlock(state.message, null)
        is LoadState.Ready -> Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Box(Modifier.size(8.dp).clip(RoundedCornerShape(50)).background(if (state.value.enabled) Positive else Warning))
                Spacer(Modifier.width(8.dp))
                Text(if (state.value.enabled) "ENABLED" else "DISABLED", style = MaterialTheme.typography.labelSmall)
                Spacer(Modifier.weight(1f))
                Text("${state.value.accountCount} ACCOUNTS", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Text("${state.value.cadence} / ${state.value.delivery}", color = MaterialTheme.colorScheme.onSurfaceVariant)
            state.value.findings.forEach { Text("${it.severity.uppercase()} / ${it.title}") }
            OutlinedButton(onClick = run, enabled = state.value.accountCount > 0, shape = RoundedCornerShape(6.dp)) {
                Icon(Icons.Default.PlayArrow, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Run review")
            }
        }
    }
}

@Composable
private fun AccountScreen(model: AppViewModel) {
    val user = (model.session as? SessionState.SignedIn)?.user ?: return
    var showDeleteDialog by remember { mutableStateOf(false) }
    LazyColumn(Modifier.fillMaxSize()) {
        item { ScreenHeader(stringResource(R.string.account), "SECURITY / PREFERENCES") }
        item {
            Column(Modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                Text(user.name, style = MaterialTheme.typography.headlineSmall)
                Text(user.email, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text("${user.plan.uppercase()} / ${user.credits} CREDITS", style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
            }
        }
        item { SectionTitle("01", stringResource(R.string.language), null) }
        item {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(16.dp)) {
                listOf("en" to R.string.english, "zh" to R.string.chinese).forEachIndexed { index, (code, label) ->
                    SegmentedButton(
                        selected = model.language == code,
                        onClick = { model.updateLanguage(code) },
                        shape = SegmentedButtonDefaults.itemShape(index, 2),
                    ) { Text(stringResource(label)) }
                }
            }
        }
        item { SectionTitle("02", stringResource(R.string.theme), null) }
        item {
            SingleChoiceSegmentedButtonRow(Modifier.fillMaxWidth().padding(16.dp)) {
                val modes = listOf(ThemeMode.SYSTEM to R.string.system_theme, ThemeMode.LIGHT to R.string.light_theme, ThemeMode.DARK to R.string.dark_theme)
                modes.forEachIndexed { index, (mode, label) ->
                    SegmentedButton(
                        selected = model.themeMode == mode,
                        onClick = { model.setTheme(mode) },
                        shape = SegmentedButtonDefaults.itemShape(index, modes.size),
                    ) { Text(stringResource(label), maxLines = 1) }
                }
            }
        }
        item { SectionTitle("03", stringResource(R.string.research_safety_section), "SERVER GATED") }
        item { ServiceCapabilityRows(model) }
        item {
            TextButton(onClick = model::signOut, modifier = Modifier.fillMaxWidth().padding(16.dp)) {
                Icon(Icons.AutoMirrored.Filled.ExitToApp, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.sign_out), color = Negative)
            }
        }
        item {
            TextButton(
                onClick = { showDeleteDialog = true },
                modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
            ) {
                Icon(Icons.Default.Delete, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text(stringResource(R.string.delete_account), color = Negative)
            }
        }
        item { Disclosure() }
    }

    if (showDeleteDialog) {
        AlertDialog(
            onDismissRequest = { showDeleteDialog = false },
            title = { Text(stringResource(R.string.delete_account_confirm_title)) },
            text = { Text(stringResource(R.string.delete_account_confirm_message)) },
            confirmButton = {
                TextButton(
                    onClick = {
                        showDeleteDialog = false
                        model.deleteAccount()
                    },
                ) {
                    Text(stringResource(R.string.delete_account_confirm), color = Negative)
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteDialog = false }) {
                    Text(stringResource(R.string.cancel))
                }
            },
        )
    }
}

/**
 * 服务能力状态行（服务端为准）：可用 → 打开受信 Web 产品路由；不可用 → 灰色不可操作。
 * LIVE 恒为 Disabled，永不渲染任何启动/操作按钮。
 */
@Composable
private fun ServiceCapabilityRows(model: AppViewModel) {
    val capabilities = (model.mobileCapabilities as? LoadState.Ready)?.value
    val contractAvailable = capabilities?.serverContractAvailable == true

    fun route(relative: String) {
        model.openProductRoute(if (model.language == "zh") "zh/$relative" else "en/$relative")
    }

    Column(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 6.dp)) {
        ServiceCapabilityRow(
            icon = Icons.Default.Psychology,
            title = stringResource(R.string.memory_controls),
            subtitle = when {
                !contractAvailable -> stringResource(R.string.feature_not_available_yet)
                capabilities?.memoryServiceEnabled != true -> stringResource(R.string.feature_disabled_for_account)
                else -> stringResource(R.string.open_in_web)
            },
            enabled = contractAvailable && capabilities.memoryServiceEnabled == true && capabilities.userCanManageMemory == true,
            onClick = { route("account/memory") },
        )
        ServiceCapabilityRow(
            icon = Icons.Default.Shield,
            title = stringResource(R.string.trading_safety),
            subtitle = when {
                !contractAvailable -> stringResource(R.string.feature_not_available_yet)
                capabilities?.autoTradingEnabled != true -> stringResource(R.string.feature_disabled_for_account)
                else -> stringResource(R.string.open_in_web)
            },
            enabled = contractAvailable && capabilities.autoTradingEnabled == true && capabilities.userCanViewTradingMandates == true,
            onClick = { route("account/trading") },
        )
        ServiceCapabilityRow(
            icon = Icons.Default.Lock,
            title = stringResource(R.string.live_trading_row),
            subtitle = stringResource(R.string.live_trading_disabled_caption),
            enabled = false,
            onClick = {},
        )
    }
}

@Composable
private fun ServiceCapabilityRow(
    icon: ImageVector,
    title: String,
    subtitle: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Row(
        Modifier.fillMaxWidth().clickable(enabled = enabled, onClick = onClick).padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Icon(icon, contentDescription = null, tint = if (enabled) Positive else MaterialTheme.colorScheme.onSurfaceVariant)
        Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f)) {
            Text(title, fontWeight = FontWeight.SemiBold, color = if (enabled) MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
            Text(subtitle, style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if (enabled) Icon(Icons.Default.ChevronRight, contentDescription = null, tint = MaterialTheme.colorScheme.onSurfaceVariant)
    }
}

@Composable
private fun MarkdownBody(markdown: String) {
    Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
        markdown.lineSequence().filter { it.isNotBlank() }.take(100).forEach { raw ->
            val line = raw.trim()
            when {
                line.startsWith("### ") -> Text(line.removePrefix("### "), style = MaterialTheme.typography.titleMedium)
                line.startsWith("## ") -> Text(line.removePrefix("## "), style = MaterialTheme.typography.titleMedium)
                line.startsWith("# ") -> Text(line.removePrefix("# "), style = MaterialTheme.typography.headlineSmall)
                line.startsWith("|") -> Text(line.trim('|').replace("|", "   "), fontFamily = FontFamily.Monospace, style = MaterialTheme.typography.bodySmall, modifier = Modifier.horizontalScroll(rememberScrollState()))
                line.startsWith("-") || line.startsWith("*") -> Text("- ${line.drop(1).trim().replace("**", "")}")
                else -> Text(line.replace("**", "").replace("__", ""))
            }
        }
    }
}

@Composable
private fun Disclosure(text: String = stringResource(R.string.risk_disclosure)) {
    Text(text, modifier = Modifier.padding(16.dp), style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
}

@Composable
private fun LoadingBlock(modifier: Modifier = Modifier) {
    Box(modifier.fillMaxWidth().heightIn(min = 110.dp), contentAlignment = Alignment.Center) { CircularProgressIndicator(Modifier.size(24.dp), strokeWidth = 2.dp) }
}

@Composable
private fun ErrorBlock(message: String, retry: (() -> Unit)?, modifier: Modifier = Modifier) {
    Column(modifier.fillMaxWidth().padding(16.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Text(message, color = Negative)
        retry?.let { TextButton(onClick = it) { Text(stringResource(R.string.retry)) } }
    }
}

@Composable
private fun InlineError(message: String, close: () -> Unit) {
    Row(Modifier.fillMaxWidth().background(MaterialTheme.colorScheme.errorContainer, RoundedCornerShape(6.dp)).padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(message, Modifier.weight(1f), color = MaterialTheme.colorScheme.onErrorContainer)
        IconButton(onClick = close) { Icon(Icons.Default.Close, contentDescription = null) }
    }
}

@Composable
private fun EmptyBlock() {
    Text(stringResource(R.string.no_data), Modifier.fillMaxWidth().padding(16.dp), color = MaterialTheme.colorScheme.onSurfaceVariant)
}

private fun money(value: Double?): String {
    if (value == null || !value.isFinite()) return "-"
    return NumberFormat.getCurrencyInstance(Locale.US).apply { currency = Currency.getInstance("USD") }.format(value)
}

private fun percent(value: Double?): String = value?.let { "%+.2f%%".format(Locale.US, it) } ?: "-"

private fun date(value: java.time.Instant?): String = value?.atZone(ZoneId.systemDefault())
    ?.format(DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm")) ?: "-"
