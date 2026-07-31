package ai.puregamma.android.ui

import android.Manifest
import android.annotation.SuppressLint
import android.content.ActivityNotFoundException
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.webkit.CookieManager
import android.webkit.JavascriptInterface
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
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
        setAcceptThirdPartyCookies(this@configureProductWebView, true)
    }
    addJavascriptInterface(ReplyHapticBridge(context.applicationContext), "PureGammaAndroid")
    webChromeClient = chromeClient
    webViewClient = ProductWebViewClient(context, onSignOut)
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
    override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
        val uri = request.url
        if (uri.host == "app.puregamma.ai" && uri.path.orEmpty().matches(Regex("^/(en|zh)/login/?$"))) {
            onSignOut()
            return true
        }
        if (uri.scheme == "https" && (uri.host == "app.puregamma.ai" || uri.host == "api.puregamma.ai")) return false
        if (uri.scheme in setOf("http", "https", "mailto", "tel")) {
            try {
                context.startActivity(Intent(Intent.ACTION_VIEW, uri))
            } catch (_: ActivityNotFoundException) {
                // Keep the product usable if the device has no external handler.
            }
        }
        return true
    }
}
