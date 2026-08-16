package ai.puregamma.android.data.remote

import okhttp3.Interceptor
import okhttp3.Response
import org.json.JSONObject

/**
 * Maps structured JSON API errors to [RetrofitApiException] so callers can
 * branch on status/code without re-parsing bodies.
 *
 * - 2xx and non-JSON error bodies pass through untouched.
 * - `{"detail":{"code","message"|"reason"}}` -> RetrofitApiException(status,
 *   message, code).
 * - `{"detail":"plain string"}` -> RetrofitApiException(status, text, null).
 *
 * Note (2.2): this interceptor is unit-tested standalone; wiring it into the
 * production OkHttpClient in ApiProvider is a follow-up so 2.2 keeps the
 * exact current runtime error behavior.
 */
class ApiErrorInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.isSuccessful) return response
        val contentType = response.body?.contentType()?.toString() ?: ""
        if (!contentType.contains("json")) return response

        val bodyText = response.peekBody(Long.MAX_VALUE).string()

        val detail = try {
            JSONObject(bodyText).opt("detail")
        } catch (_: Exception) {
            return response
        }
        if (detail == null || detail == JSONObject.NULL) return response

        if (detail is JSONObject) {
            val code = detail.optString("code").takeIf { it.isNotBlank() }
            val message = detail.optString("message").takeIf { it.isNotBlank() }
                ?: detail.optString("reason").takeIf { it.isNotBlank() }
            throw RetrofitApiException(response.code, message ?: response.message, code)
        }
        val plain = detail.toString().takeIf { it.isNotBlank() }
        throw RetrofitApiException(response.code, plain ?: response.message, null)
    }
}
