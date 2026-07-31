package ai.puregamma.android.data.remote

import ai.puregamma.android.BuildConfig
import ai.puregamma.android.data.local.SecureTokenStore
import com.google.gson.Gson
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.BufferedReader
import kotlin.coroutines.coroutineContext

data class ServerEvent(val name: String, val data: JsonObject)

class SseClient(
    private val client: OkHttpClient,
    private val gson: Gson = Gson(),
) {

    suspend fun stream(
        path: String,
        body: Any,
        onEvent: suspend (ServerEvent) -> Unit,
    ) = withContext(Dispatchers.IO) {
        val baseUrl = BuildConfig.API_BASE_URL.trimEnd('/')
        val json = gson.toJson(body)
        val requestBody = json.toRequestBody("application/json".toMediaType())

        val request = Request.Builder()
            .url(baseUrl + path)
            .post(requestBody)
            .header("Accept", "text/event-stream")
            .header("Content-Type", "application/json")
            .build()

        val response = client.newCall(request).execute()
        response.use { resp ->
            if (!resp.isSuccessful) {
                val errorBody = resp.body?.string().orEmpty()
                throw RetrofitApiException(resp.code, parseErrorMessage(errorBody))
            }
            resp.body?.byteStream()?.bufferedReader()?.use { reader ->
                parseEvents(reader, onEvent)
            }
        }
    }

    private suspend fun parseEvents(reader: BufferedReader, onEvent: suspend (ServerEvent) -> Unit) {
        var eventName = "message"
        val data = StringBuilder()
        while (true) {
            coroutineContext.ensureActive()
            val line = reader.readLine() ?: break
            when {
                line.startsWith("event:") -> eventName = line.substringAfter(':').trim()
                line.startsWith("data:") -> {
                    if (data.isNotEmpty()) data.append('\n')
                    data.append(line.substringAfter(':').trimStart())
                }
                line.isBlank() && data.isNotEmpty() -> {
                    val parsed = runCatching { JsonParser.parseString(data.toString()).asJsonObject }.getOrElse { JsonObject() }
                    onEvent(ServerEvent(eventName, parsed))
                    eventName = "message"
                    data.clear()
                }
            }
        }
        if (data.isNotEmpty()) {
            val parsed = runCatching { JsonParser.parseString(data.toString()).asJsonObject }.getOrElse { JsonObject() }
            onEvent(ServerEvent(eventName, parsed))
        }
    }

    private fun parseErrorMessage(body: String): String {
        return runCatching {
            val json = JsonParser.parseString(body).asJsonObject
            val detail = json.get("detail")
            when {
                detail == null -> body
                detail.isJsonObject -> detail.asJsonObject.get("message")?.asString ?: "Request failed"
                detail.isJsonPrimitive -> detail.asString
                else -> body
            }
        }.getOrDefault(body)
    }
}
