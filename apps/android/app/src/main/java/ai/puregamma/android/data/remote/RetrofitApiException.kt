package ai.puregamma.android.data.remote

import com.google.gson.JsonElement
import com.google.gson.JsonParser

/**
 * A refused API call. [detail] keeps the whole error envelope — the code and
 * every extra field (`runId`, `messageId`, ...) — so callers branch on data,
 * not on message text. See docs/mobile/MOBILE_API_CONTRACT.md §0 and §9.
 */
class RetrofitApiException(
    val status: Int,
    override val message: String,
    val code: String? = null,
    val detail: ApiErrorDetail? = null,
) : Exception(message) {
    companion object {
        fun fromBody(status: Int, body: String, fallback: String = "Request failed ($status)"): RetrofitApiException {
            val detail = ApiErrorDetail.parse(status, body)
            return RetrofitApiException(status, detail.message ?: detail.code ?: fallback, detail.code, detail)
        }
    }
}

/** The parts of a FastAPI error body a client may act on. */
data class ApiErrorDetail(
    val status: Int,
    val code: String?,
    val message: String?,
    val fields: Map<String, String> = emptyMap(),
) {
    companion object {
        private val BARE_CODE = Regex("^[A-Z][A-Z0-9_]{2,}$")

        fun parse(status: Int, body: String): ApiErrorDetail {
            val root: JsonElement = runCatching { JsonParser.parseString(body) }.getOrNull()
                ?: return ApiErrorDetail(status, null, null)
            // `{"detail": ...}`, or a bare validation array; anything else (HTML, text) has no envelope.
            val detail = when {
                root.isJsonObject -> root.asJsonObject.get("detail")
                root.isJsonArray -> root
                else -> null
            }
            return when {
                detail == null || detail.isJsonNull -> ApiErrorDetail(status, null, null)
                detail.isJsonObject -> {
                    val scalars = detail.asJsonObject.entrySet()
                        .filter { it.value.isJsonPrimitive }
                        .associate { it.key to it.value.asString }
                        .toMutableMap()
                    val code = scalars.remove("code")
                    val message = scalars.remove("message") ?: scalars.remove("reason")
                    ApiErrorDetail(status, code, message, scalars)
                }
                detail.isJsonPrimitive -> {
                    // `{"detail": "CONVERSATION_BUSY"}` is a code; `{"detail": "Conversation not found"}` is prose.
                    val text = detail.asString
                    if (BARE_CODE.matches(text)) ApiErrorDetail(status, text, null) else ApiErrorDetail(status, null, text)
                }
                detail.isJsonArray -> {
                    val first = detail.asJsonArray.firstOrNull()
                    val msg = if (first != null && first.isJsonObject) first.asJsonObject.get("msg")?.takeIf { it.isJsonPrimitive }?.asString else null
                    ApiErrorDetail(status, null, msg)
                }
                else -> ApiErrorDetail(status, null, null)
            }
        }
    }
}

/** The envelope of any failed call: our own exception, or a Retrofit HttpException's body. */
fun Throwable.apiErrorDetail(): ApiErrorDetail? = when (this) {
    is RetrofitApiException -> detail ?: ApiErrorDetail(status, code, message)
    is retrofit2.HttpException -> {
        val body = runCatching { response()?.errorBody()?.string() }.getOrNull().orEmpty()
        ApiErrorDetail.parse(code(), body)
    }
    else -> null
}
