package ai.puregamma.android.core

import android.content.Context
import ai.puregamma.android.R

/**
 * Maps API error codes to localized, human-readable messages. The backend
 * returns machine codes (e.g. RATE_LIMITED, INVALID_CREDENTIALS) that must
 * never be shown raw in the UI.
 */
object ErrorMessages {

    fun messageResFor(code: String?, status: Int): Int? = when (code) {
        "RATE_LIMITED" -> R.string.error_rate_limited
        "INVALID_CREDENTIALS" -> R.string.error_invalid_credentials
        "EMAIL_NOT_VERIFIED" -> R.string.error_email_not_verified
        "EMAIL_ALREADY_REGISTERED" -> R.string.error_email_already_registered
        "PASSWORD_TOO_WEAK" -> R.string.error_password_too_weak
        "INVALID_EMAIL" -> R.string.error_invalid_email
        "CAPTCHA_FAILED", "CAPTCHA_REQUIRED", "CAPTCHA_EXPIRED", "CAPTCHA_UNAVAILABLE" -> R.string.error_captcha
        "GOOGLE_OAUTH_NOT_CONFIGURED", "GOOGLE_VERIFICATION_FAILED" -> R.string.error_google_sign_in
        "INSUFFICIENT_CREDITS" -> R.string.error_insufficient_credits
        else -> when (status) {
            429 -> R.string.error_rate_limited
            else -> null
        }
    }

    fun resolve(context: Context, error: Throwable, fallback: String): String {
        val api = error as? ApiException
        if (api != null) {
            messageResFor(api.code, api.status)?.let { return context.getString(it) }
        }
        return error.message?.takeIf { it.isNotBlank() } ?: fallback
    }
}
