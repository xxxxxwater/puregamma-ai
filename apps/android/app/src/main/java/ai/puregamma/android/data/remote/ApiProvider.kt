package ai.puregamma.android.data.remote

import ai.puregamma.android.BuildConfig
import ai.puregamma.android.data.local.SecureTokenStore
import com.google.gson.GsonBuilder
import okhttp3.Interceptor
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import java.util.concurrent.TimeUnit

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
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val original = chain.request()
        val builder = original.newBuilder()
            .header("Accept", "application/json")
            .header("X-PG-Locale", localeProvider())
        tokenStore.read()?.let { builder.header("Authorization", "Bearer $it") }
        return chain.proceed(builder.build())
    }
}

private class AuthErrorInterceptor(
    private val onUnauthorized: () -> Unit,
) : Interceptor {
    override fun intercept(chain: Interceptor.Chain): okhttp3.Response {
        val response = chain.proceed(chain.request())
        if (response.code == 401) {
            response.close()
            onUnauthorized()
        }
        return response
    }
}
