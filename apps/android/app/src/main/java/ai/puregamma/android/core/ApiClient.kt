package ai.puregamma.android.core

import ai.puregamma.android.BuildConfig
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.io.BufferedReader
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import kotlin.coroutines.coroutineContext

class ApiException(val status: Int, override val message: String) : Exception(message)

data class ServerEvent(val name: String, val data: JSONObject)

class ApiClient(
    private val tokenStore: SecureTokenStore,
    private val localeProvider: () -> String,
    private val onUnauthorized: () -> Unit,
) {
    suspend fun get(path: String): JSONObject = request(path)

    suspend fun post(path: String, body: JSONObject = JSONObject()): JSONObject =
        request(path, "POST", body)

    suspend fun put(path: String, body: JSONObject): JSONObject = request(path, "PUT", body)

    suspend fun delete(path: String): JSONObject = request(path, "DELETE")

    suspend fun request(path: String, method: String = "GET", body: JSONObject? = null): JSONObject =
        withContext(Dispatchers.IO) {
            val connection = open(path, method, "application/json")
            try {
                if (body != null) {
                    connection.doOutput = true
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
                }
                val status = connection.responseCode
                val content = readBody(connection, status)
                validate(status, content)
                if (content.isBlank()) JSONObject() else JSONObject(content)
            } finally {
                connection.disconnect()
            }
        }

    suspend fun stream(path: String, body: JSONObject, onEvent: suspend (ServerEvent) -> Unit) =
        withContext(Dispatchers.IO) {
            val connection = open(path, "POST", "text/event-stream").apply {
                doOutput = true
                readTimeout = 120_000
                setRequestProperty("Content-Type", "application/json")
            }
            try {
                connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
                val status = connection.responseCode
                if (status !in 200..299) {
                    val content = readBody(connection, status)
                    validate(status, content)
                }
                parseEvents(connection.inputStream.bufferedReader(), onEvent)
            } finally {
                connection.disconnect()
            }
        }

    private fun open(path: String, method: String, accept: String): HttpURLConnection {
        require(path.startsWith('/'))
        val base = BuildConfig.API_BASE_URL.trimEnd('/')
        require(base.startsWith("https://")) { "PureGamma API must use HTTPS" }
        return (URL(base + path).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 20_000
            readTimeout = 20_000
            useCaches = false
            setRequestProperty("Accept", accept)
            setRequestProperty("X-PG-Locale", localeProvider())
            tokenStore.read()?.let { setRequestProperty("Authorization", "Bearer $it") }
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
                    onEvent(ServerEvent(eventName, runCatching { JSONObject(data.toString()) }.getOrElse { JSONObject() }))
                    eventName = "message"
                    data.clear()
                }
            }
        }
        if (data.isNotEmpty()) onEvent(ServerEvent(eventName, JSONObject(data.toString())))
    }

    private fun readBody(connection: HttpURLConnection, status: Int): String {
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        return stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
    }

    private fun validate(status: Int, content: String) {
        if (status in 200..299) return
        if (status == 401) onUnauthorized()
        val root = runCatching { JSONObject(content) }.getOrNull()
        val detail = root?.opt("detail")
        val message = when (detail) {
            is String -> detail
            is JSONObject -> detail.optString("message", detail.optString("code", "Request failed"))
            else -> "HTTP $status"
        }
        throw ApiException(status, message)
    }
}
