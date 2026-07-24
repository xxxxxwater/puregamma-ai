package ai.puregamma.android

import android.content.Context
import android.content.Intent
import android.util.Log

class PureGammaMessagingService : android.app.Service() {

    override fun onBind(intent: Intent?) = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent == null) return START_NOT_STICKY
        when (intent.action) {
            ACTION_TOKEN -> {
                intent.getStringExtra(EXTRA_TOKEN)?.let { PureGammaPushBridge.onTokenRefreshed(it) }
            }
            ACTION_MESSAGE -> {
                val data = mutableMapOf<String, String>()
                intent.extras?.keySet()?.forEach { key ->
                    intent.extras?.getString(key)?.let { value -> data[key] = value }
                }
                PureGammaPushBridge.onMessageReceived(data)
            }
        }
        return START_NOT_STICKY
    }

    companion object {
        private const val TAG = "PGMessagingService"
        const val ACTION_TOKEN = "ai.puregamma.push.TOKEN"
        const val ACTION_MESSAGE = "ai.puregamma.push.MESSAGE"
        const val EXTRA_TOKEN = "token"
        const val EXTRA_ROUTE = "route"
        const val EXTRA_TITLE = "title"
        const val EXTRA_BODY = "body"
        const val EXTRA_SOUND = "sound"
    }
}
