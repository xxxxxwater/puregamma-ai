package ai.puregamma.android.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ErrorMessagesTest {

    @Test
    fun knownCodesMapToFriendlyResources() {
        listOf(
            "RATE_LIMITED",
            "INVALID_CREDENTIALS",
            "EMAIL_NOT_VERIFIED",
            "EMAIL_ALREADY_REGISTERED",
            "PASSWORD_TOO_WEAK",
            "INVALID_EMAIL",
            "CAPTCHA_FAILED",
            "CAPTCHA_REQUIRED",
            "CAPTCHA_EXPIRED",
            "CAPTCHA_UNAVAILABLE",
            "GOOGLE_OAUTH_NOT_CONFIGURED",
            "GOOGLE_VERIFICATION_FAILED",
            "INSUFFICIENT_CREDITS",
        ).forEach { code ->
            assertEquals(
                "code $code must map to a friendly message resource",
                true,
                ErrorMessages.messageResFor(code, 400) != null,
            )
        }
    }

    @Test
    fun rateLimitedFallsBackOnStatusWhenCodeMissing() {
        assertEquals(true, ErrorMessages.messageResFor(null, 429) != null)
    }

    @Test
    fun unknownCodesKeepServerMessage() {
        assertNull(ErrorMessages.messageResFor("SOME_OTHER_CODE", 400))
        assertNull(ErrorMessages.messageResFor(null, 400))
    }
}
