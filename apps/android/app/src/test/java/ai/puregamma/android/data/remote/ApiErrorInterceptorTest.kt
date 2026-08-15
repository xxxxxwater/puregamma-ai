package ai.puregamma.android.data.remote

import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

class ApiErrorInterceptorTest {

    private lateinit var server: MockWebServer
    private lateinit var client: OkHttpClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = OkHttpClient.Builder()
            .addInterceptor(ApiErrorInterceptor())
            .build()
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun successfulJsonPassesThrough() {
        server.enqueue(MockResponse().setResponseCode(200).setBody("""{"ok":true}"""))
        val response = client.newCall(request()).execute()
        assertEquals(200, response.code)
        assertEquals("""{"ok":true}""", response.body?.string())
    }

    @Test
    fun structuredErrorThrowsWithCodeAndMessage() {
        server.enqueue(
            MockResponse()
                .setResponseCode(400)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":{"code":"INVALID_EMAIL","message":"Please enter a valid email"}}"""),
        )
        try {
            client.newCall(request()).execute()
            fail("expected RetrofitApiException")
        } catch (e: RetrofitApiException) {
            assertEquals(400, e.status)
            assertEquals("INVALID_EMAIL", e.code)
            assertEquals("Please enter a valid email", e.message)
        }
    }

    @Test
    fun plainStringDetailBecomesMessage() {
        server.enqueue(
            MockResponse()
                .setResponseCode(429)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":"Too many attempts"}"""),
        )
        try {
            client.newCall(request()).execute()
            fail("expected RetrofitApiException")
        } catch (e: RetrofitApiException) {
            assertEquals(429, e.status)
            assertNull(e.code)
            assertEquals("Too many attempts", e.message)
        }
    }

    @Test
    fun reasonFallbackWhenMessageMissing() {
        server.enqueue(
            MockResponse()
                .setResponseCode(400)
                .setHeader("Content-Type", "application/json")
                .setBody("""{"detail":{"code":"CEX_PERMISSION_DENIED","reason":"read-only keys only"}}"""),
        )
        try {
            client.newCall(request()).execute()
            fail("expected RetrofitApiException")
        } catch (e: RetrofitApiException) {
            assertEquals("CEX_PERMISSION_DENIED", e.code)
            assertEquals("read-only keys only", e.message)
        }
    }

    @Test
    fun nonJsonErrorPassesThrough() {
        server.enqueue(
            MockResponse()
                .setResponseCode(502)
                .setHeader("Content-Type", "text/html")
                .setBody("<html>gateway error</html>"),
        )
        val response = client.newCall(request()).execute()
        assertEquals(502, response.code)
    }

    private fun request(): Request = Request.Builder()
        .url(server.url("/test"))
        .build()
}
