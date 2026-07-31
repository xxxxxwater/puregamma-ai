package ai.puregamma.android

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import java.util.concurrent.CopyOnWriteArrayList

object PureGammaPushBridge {

    private val onTokenListeners = CopyOnWriteArrayList<(String) -> Unit>()
    private val onMessageListeners = CopyOnWriteArrayList<(Map<String, String>) -> Unit>()
    @Volatile private var lastToken: String? = null
    @Volatile private var frozen = false

    fun addTokenListener(listener: (String) -> Unit) {
        onTokenListeners.add(listener)
        lastToken?.let { listener(it) }
    }

    fun removeTokenListener(listener: (String) -> Unit) {
        onTokenListeners.remove(listener)
    }

    fun addMessageListener(listener: (Map<String, String>) -> Unit) {
        onMessageListeners.add(listener)
    }

    fun removeMessageListener(listener: (Map<String, String>) -> Unit) {
        onMessageListeners.remove(listener)
    }

    fun onTokenRefreshed(token: String) {
        if (frozen) return
        lastToken = token
        onTokenListeners.forEach { it(token) }
    }

    fun onMessageReceived(data: Map<String, String>) {
        if (frozen) return
        onMessageListeners.forEach { it(data) }
    }

    fun freeze() {
        frozen = true
    }

    fun createNotificationChannel(application: Application) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Alerts",
                NotificationManager.IMPORTANCE_DEFAULT,
            ).apply {
                description = "Portfolio alerts and research notifications"
            }
            application.getSystemService(NotificationManager::class.java)
                .createNotificationChannel(channel)
        }
    }

    const val CHANNEL_ID = "puregamma_alerts"
}
