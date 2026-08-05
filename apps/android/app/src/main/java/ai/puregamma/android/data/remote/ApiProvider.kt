package ai.puregamma.android.data.remote

import ai.puregamma.android.BuildConfig
import ai.puregamma.android.data.local.SecureTokenStore
import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.io.IOException
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean

object ApiProvider {

    private const val CONNECT_TIMEOUT = 20L
    private const val READ_TIMEOUT = 20L

    fun create(tokenStore: SecureTokenStore, localeProvider: () -> String, onUnauthorized: () -> Unit): PureGammaApi {
        val gson = GsonBuilder().serializeNulls().create()
        return Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL.trimEnd('/') + "/")
            .client(createOkHttpClient(tokenStore, localeProvider, onUnauthorized))
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
            .create(PureGammaApi::class.java)
    }

    fun createOkHttpClient(
        tokenStore: SecureTokenStore,
        localeProvider: () -> String,
        onUnauthorized: () -> Unit,
    ): OkHttpClient {
        return OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT, TimeUnit.SECONDS)
            .readTimeout(READ_TIMEOUT, TimeUnit.SECONDS)
            .addInterceptor(HeaderInterceptor(tokenStore, localeProvider))
            .addInterceptor(ApiErrorInterceptor())
            .addInterceptor(AuthErrorInterceptor(onUnauthorized))
            .addInterceptor(
                HttpLoggingInterceptor().apply {
                    level = if (BuildConfig.DEBUG) {
                        HttpLoggingInterceptor.Level.HEADERS
                    } else {
                        HttpLoggingInterceptor.Level.NONE
                    }
                    redactHeader("Authorization")
                },
            )
            .build()
    }

    fun createStreamOkHttpClient(
        tokenStore: SecureTokenStore,
        localeProvider: () -> String,
        onUnauthorized: () -> Unit,
    ): OkHttpClient {
        return OkHttpClient.Builder()
            .connectTimeout(CONNECT_TIMEOUT, TimeUnit.SECONDS)
            .readTimeout(120L, TimeUnit.SECONDS)
            .addInterceptor(HeaderInterceptor(tokenStore, localeProvider))
            .addInterceptor(AuthErrorInterceptor(onUnauthorized))
            .build()
    }
}

private class HeaderInterceptor(
    private val tokenStore: SecureTokenStore,
    private val localeProvider: () -> String,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()
        val builder = original.newBuilder()
            .header("Accept", "application/json")
            .header("X-PG-Locale", localeProvider())
        tokenStore.read()?.let { builder.header("Authorization", "Bearer $it") }
        return chain.proceed(builder.build())
    }
}

/**
 * Signs the user out exactly once on the first 401. The response is passed
 * through untouched so Retrofit/SseClient can surface a real HTTP error
 * instead of an IllegalStateException from a closed body.
 */
private class AuthErrorInterceptor(
    private val onUnauthorized: () -> Unit,
) : Interceptor {
    private val signedOut = AtomicBoolean(false)

    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.code == 401 && signedOut.compareAndSet(false, true)) {
            onUnauthorized()
        }
        return response
    }
}

/**
 * Converts structured FastAPI errors ({detail: {code, message}} or plain
 * string detail) into [RetrofitApiException] so every repository surfaces a
 * friendly, localized message. Non-JSON bodies fall through to Retrofit.
 */
internal class ApiErrorInterceptor : Interceptor {
    override fun intercept(chain: Interceptor.Chain): Response {
        val response = chain.proceed(chain.request())
        if (response.isSuccessful) return response
        val contentType = response.body?.contentType()
        val isJson = contentType != null &&
            (contentType.subtype == "json" || contentType.subtype.endsWith("+json"))
        if (!isJson) return response

        val raw = try {
            response.peekBody(8 * 1024).string()
        } catch (_: IOException) {
            return response
        }
        val parsed = runCatching { JsonParser.parseString(raw).asJsonObject }.getOrNull()
            ?: return response
        val detail = parsed.get("detail")
        val code = when {
            detail != null && detail.isJsonObject -> detail.asJsonObject.get("code")?.asString
            else -> null
        }
        val message = when {
            detail != null && detail.isJsonPrimitive -> detail.asString
            detail != null && detail.isJsonObject -> {
                detail.asJsonObject.get("message")?.asString?.takeIf { it.isNotBlank() }
                    ?: detail.asJsonObject.get("reason")?.asString
                    ?: code ?: "Request failed"
            }
            else -> null
        }
        if (message == null && code == null) return response
        throw RetrofitApiException(
            status = response.code,
            message = message ?: "Request failed",
            code = code,
        )
    }
}
