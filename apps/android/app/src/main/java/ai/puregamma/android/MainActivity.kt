package ai.puregamma.android

import android.content.Intent
import android.content.ActivityNotFoundException
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.LocalActivityResultRegistryOwner
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.browser.customtabs.CustomTabsIntent
import androidx.compose.runtime.CompositionLocalProvider
import ai.puregamma.android.ui.PureGammaApp
import android.widget.Toast

class MainActivity : ComponentActivity() {
    private val model: AppViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            // Compose's current activity artifact does not automatically provide this
            // owner on every device image; WebView microphone permission needs it.
            CompositionLocalProvider(LocalActivityResultRegistryOwner provides this@MainActivity) {
                PureGammaApp(
                    model = model,
                    openBrowser = ::openBrowser,
                )
            }
        }
        intent?.data?.let(model::handleOAuth)
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        setIntent(intent)
        intent.data?.let(model::handleOAuth)
    }

    private fun openBrowser(uri: Uri) {
        try {
            val chromeIntent = Intent(Intent.ACTION_VIEW, uri)
                .addCategory(Intent.CATEGORY_BROWSABLE)
                .setPackage(CHROME_PACKAGE)
            startActivity(CustomTabsIntent.setAlwaysUseBrowserUI(chromeIntent))
        } catch (_: ActivityNotFoundException) {
            Toast.makeText(this, R.string.chrome_required, Toast.LENGTH_LONG).show()
            runCatching {
                startActivity(
                    Intent(Intent.ACTION_VIEW, Uri.parse("market://details?id=$CHROME_PACKAGE"))
                        .setPackage(PLAY_STORE_PACKAGE),
                )
            }
        }
    }

    private companion object {
        const val CHROME_PACKAGE = "com.android.chrome"
        const val PLAY_STORE_PACKAGE = "com.android.vending"
    }
}
