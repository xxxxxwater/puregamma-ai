package ai.puregamma.android

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64

object MobileOAuth {
    const val CALLBACK_URL = "puregamma://oauth/callback"

    fun random(byteCount: Int): String {
        val bytes = ByteArray(byteCount).also(SecureRandom()::nextBytes)
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes)
    }

    fun challenge(verifier: String): String {
        val digest = MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII))
        return Base64.getUrlEncoder().withoutPadding().encodeToString(digest)
    }
}
