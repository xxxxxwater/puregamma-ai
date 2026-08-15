package ai.puregamma.android.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import android.webkit.WebViewClient
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.viewinterop.AndroidView
import androidx.core.content.ContextCompat
import ai.puregamma.android.BuildConfig
import java.io.ByteArrayInputStream

/**
 * Production product surface. The server exchanges the native session for an
 * HttpOnly cookie before this URL loads, so WebView never receives a JWT.
 */
@Composable
fun WebProductScreen(entryUrl: String, onSignOut: () -> Unit) {
    val context = LocalContext.current
    var pendingAudioRequest by remember { mutableStateOf<PermissionRequest?>(null) }
    val microphonePermission = rememberLauncherForActivityResult(
        ActivityResultContracts.RequestPermission(),
    ) { granted ->
        pendingAudioRequest?.let { request ->
            if (granted) request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) else request.deny()
        }
        pendingAudioRequest = null
    }

    val chromeClient = remember(context, microphonePermission) {
        object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) {
                if (!request.resources.contains(PermissionRequest.RESOURCE_AUDIO_CAPTURE)) {
                    request.deny()
                    return
                }
                if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                    request.grant(arrayOf(PermissionRequest.RESOURCE_AUDIO_CAPTURE))
                } else {
                    pendingAudioRequest = request
                    microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
                }
            }

            override fun onPermissionRequestCanceled(request: PermissionRequest) {
                if (pendingAudioRequest == request) pendingAudioRequest = null
            }
        }
    }

    AndroidView(
        modifier = Modifier.fillMaxSize(),
        factory = {
            WebView(it).apply {
                configureProductWebView(context, chromeClient, onSignOut)
                loadUrl(entryUrl)
            }
        },
        update = { webView ->
            if (webView.url != entryUrl && webView.url == null) webView.loadUrl(entryUrl)
        },
    )
}

@SuppressLint("SetJavaScriptEnabled")
private fun WebView.configureProductWebView(
    context: Context,
    chromeClient: WebChromeClient,
    onSignOut: () -> Unit,
) {
    setBackgroundColor(Color.rgb(3, 3, 3))
    settings.apply {
        javaScriptEnabled = true
        domStorageEnabled = true
        databaseEnabled = true
        mediaPlaybackRequiresUserGesture = false
        javaScriptCanOpenWindowsAutomatically = true
        setSupportMultipleWindows(false)
        allowFileAccess = false
        allowContentAccess = false
        mixedContentMode = android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW
        userAgentString = "$userAgentString PureGammaAndroid/${BuildConfig.VERSION_NAME}"
    }
    CookieManager.getInstance().apply {
        setAcceptCookie(true)
        // 第三方 Cookie 保持开启是既有登录流程需要（Web 产品的 OAuth/会话）。
        // 防护边界：① 只加载白名单域名；② 顶层导航重定向重新校验；
        // ③ 注销时 removeAllCookies；④ 不允许任意自定义 Scheme 页面写入。
        setAcceptThirdPartyCookies(this@configureProductWebView, true)
    }
    addJavascriptInterface(ReplyHapticBridge(context.applicationContext), "PureGammaAndroid")
    webChromeClient = chromeClient
    webViewClient = ProductWebViewClient(context, onSignOut)
    // 阻断下载：产品 WebView 不扩展文件下载权限。
    setDownloadListener { _, _, _, _, _ -> }
    WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
}

private class ReplyHapticBridge(private val context: Context) {
    @JavascriptInterface
    fun replyCompleted() {
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            context.getSystemService(VibratorManager::class.java)?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        } ?: return
        if (vibrator.hasVibrator()) {
            vibrator.vibrate(VibrationEffect.createOneShot(18L, 45))
        }
    }
}

private class ProductWebViewClient(
    private val context: Context,
    private val onSignOut: () -> Unit,
) : WebViewClient() {
    /** 受信域名从 BuildConfig 派生（生产为 app.puregamma.ai / api.puregamma.ai），不做硬编码扩散。 */
    private val productHost: String? = runCatching { Uri.parse(BuildConfig.PRODUCT_WEB_BASE_URL).host }.getOrNull()
    private val apiHost: String? = runCatching { Uri.parse(BuildConfig.API_BASE_URL).host }.getOrNull()

    private companion object {
        val BLOCKED_SCHEMES = setOf("javascript", "file", "content", "data")
        val MAILTO_PATTERN = Regex("^[A-Za-z0-9+_.%+-]{1,64}$")
        val TEL_PATTERN = Regex("^[0-9+*#,;]{1,32}$")
    }

    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val uri = request.url
        val scheme = uri.scheme?.lowercase()
        // 明确禁止危险 Scheme（javascript/file/content/data/任意自定义 Scheme）。
        if (scheme == null || scheme in BLOCKED_SCHEMES) return true
        if (uri.host == productHost && uri.path.orEmpty().matches(Regex("^/(en|zh)/login/?$"))) {
            onSignOut()
            return true
        }
        if (scheme == "https" && (uri.host == productHost || uri.host == apiHost)) return false
        // 仅允许最简单形式的 mailto/tel（无参数、无多地址），防止参数滥用。
        if (scheme == "mailto" && uri.query == null && uri.path != null && MAILTO_PATTERN.matches(uri.path.orEmpty())) {
            openExternally(uri)
            return true
        }
        if (scheme == "tel" && uri.query == null && uri.path != null && TEL_PATTERN.matches(uri.path.orEmpty())) {
            openExternally(uri)
            return true
        }
        // 其余外链统一交给系统浏览器（仍不在此 WebView 内加载）。
        if (scheme == "http" || scheme == "https") openExternally(uri)
        return true
    }

    /**
     * 主框架资源请求重新校验：重定向后的最终 URL 仍必须是受信域名 + HTTPS。
     * 子资源（CDN 字体/图片等）不受影响。
     */
    override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
        if (request.isForMainFrame) {
            val uri = request.url
            val allowed = uri.scheme == "https" && (uri.host == productHost || uri.host == apiHost)
            if (!allowed) {
                return WebResourceResponse("text/plain", "utf-8", 403, "Blocked", emptyMap(), ByteArrayInputStream(ByteArray(0)))
            }
        }
        return null
    }

    private fun openExternally(uri: Uri) {
        try {
            context.startActivity(Intent(Intent.ACTION_VIEW, uri))
        } catch (_: ActivityNotFoundException) {
            // Keep the product usable if the device has no external handler.
        }
    }
}
