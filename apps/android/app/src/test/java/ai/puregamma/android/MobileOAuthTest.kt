package ai.puregamma.android

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.security.MessageDigest
import java.util.Base64

class MobileOAuthTest {
    @Test
    fun pkceChallengeUsesSha256Base64UrlWithoutPadding() {
        val verifier = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._~"
        val expected = Base64.getUrlEncoder().withoutPadding().encodeToString(
            MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)),
        )

        assertEquals(expected, MobileOAuth.challenge(verifier))
        assertFalse(MobileOAuth.challenge(verifier).contains('='))
    }

    @Test
    fun randomVerifierMeetsBackendMinimumLength() {
        val value = MobileOAuth.random(48)
        assertTrue(value.length >= 43)
        assertFalse(value.contains('='))
    }

    @Test
    fun randomProducesDistinctValues() {
        val a = MobileOAuth.random(32)
        val b = MobileOAuth.random(32)
        assertTrue(a != b)
    }
}
