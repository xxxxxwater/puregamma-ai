package ai.puregamma.android.core

import android.content.Context
import android.net.Uri
import ai.puregamma.android.model.User
import ai.puregamma.android.model.toUser
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64

class MobileOAuth(
    context: Context,
    private val api: ApiClient,
    private val tokenStore: SecureTokenStore,
) {
    private val pending = context.getSharedPreferences("pg_oauth_pending", Context.MODE_PRIVATE)

    suspend fun beginGoogle(): Uri {
        val verifier = random(48)
        val state = random(32)
        val nonce = random(32)
        pending.edit()
            .putString(KEY_VERIFIER, verifier)
            .putString(KEY_STATE, state)
            .putString(KEY_NONCE, nonce)
            .commit()
        val response = api.post(
            "/auth/mobile/google/start",
            JSONObject()
                .put("redirect_uri", CALLBACK_URL)
                .put("code_challenge", challenge(verifier))
                .put("client_state", state)
                .put("nonce", nonce),
        )
        return Uri.parse(response.getString("auth_url"))
    }

    suspend fun exchange(callback: Uri): User {
        require(callback.scheme == "puregamma" && callback.host == "oauth" && callback.path == "/callback")
        val state = pending.getString(KEY_STATE, null) ?: error("OAuth session expired")
        val verifier = pending.getString(KEY_VERIFIER, null) ?: error("OAuth session expired")
        val nonce = pending.getString(KEY_NONCE, null) ?: error("OAuth session expired")
        require(callback.getQueryParameter("state") == state) { "OAuth state verification failed" }
        callback.getQueryParameter("error")?.let { error("Google sign-in was canceled") }
        val code = callback.getQueryParameter("code") ?: error("OAuth callback did not contain a code")
        val response = api.post(
            "/auth/mobile/google/exchange",
            JSONObject()
                .put("code", code)
                .put("code_verifier", verifier)
                .put("nonce", nonce),
        )
        tokenStore.save(response.getString("access_token"))
        clearPending()
        return response.getJSONObject("user").toUser()
    }

    fun clearPending() {
        pending.edit().clear().apply()
    }

    companion object {
        const val CALLBACK_URL = "puregamma://oauth/callback"
        private const val KEY_VERIFIER = "verifier"
        private const val KEY_STATE = "state"
        private const val KEY_NONCE = "nonce"

        internal fun random(byteCount: Int): String {
            val bytes = ByteArray(byteCount).also(SecureRandom()::nextBytes)
            return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
        }

        internal fun challenge(verifier: String): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII))
            return Base64.getUrlEncoder().withoutPadding().encodeToString(digest)
        }
    }
}
