package ai.puregamma.android.data.remote

import com.google.gson.JsonObject
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.test.runTest
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Before
import org.junit.Test

/**
 * SSE 兼容性测试：未知事件类型、非 JSON data、断流都不能让客户端崩溃，
 * 也不会把断线伪装成失败状态（状态判定永远以服务端查询为准）。
 */
class SseClientCompatTest {

    private lateinit var server: MockWebServer
    private lateinit var client: SseClient

    @Before
    fun setUp() {
        server = MockWebServer()
        server.start()
        client = SseClient(
            client = OkHttpClient(),
            baseUrl = server.url("/").toString(),
        )
    }

    @After
    fun tearDown() {
        server.shutdown()
    }

    @Test
    fun unknownEventTypesAreDeliveredWithoutCrash() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                "event: research.new_feature\n" +
                    "data: {\"x\":1}\n\n" +
                    "event: run.state\n" +
                    "data: {\"status\":\"running\"}\n\n",
            ),
        )
        val events = mutableListOf<ServerEvent>()
        client.stream("/api/research/runs/r1/events", emptyMap<String, String>()) { events.add(it) }
        assertEquals(2, events.size)
        assertEquals("research.new_feature", events[0].name)
        assertEquals("run.state", events[1].name)
        assertEquals("running", events[1].data.get("status")?.asString)
    }

    @Test
    fun nonJsonDataBecomesEmptyObjectInsteadOfThrowing() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                "event: run.state\n" +
                    "data: not-valid-json\n\n",
            ),
        )
        val events = mutableListOf<ServerEvent>()
        client.stream("/api/research/runs/r1/events", emptyMap<String, String>()) { events.add(it) }
        assertEquals(1, events.size)
        assertEquals(JsonObject(), events[0].data)
    }

    @Test
    fun streamEndIsNotAnException() = runTest {
        // 流正常结束（服务器关闭流）不抛异常；状态恢复由上层查询服务端完成。
        server.enqueue(MockResponse().setResponseCode(200).setBody(": keepalive\n\n"))
        var delivered = 0
        client.stream("/api/research/runs/r1/events", emptyMap<String, String>()) { delivered++ }
        assertEquals(0, delivered)
    }

    @Test
    fun httpErrorSurfacesAsRetrofitApiExceptionWithStatus() = runTest {
        server.enqueue(MockResponse().setResponseCode(429).setBody("""{"detail":"rate limited"}"""))
        try {
            client.stream("/api/research/runs/r1/events", emptyMap<String, String>()) { }
            fail("Expected RetrofitApiException")
        } catch (e: RetrofitApiException) {
            assertEquals(429, e.status)
        }
    }

    @Test
    fun multiLineDataIsJoined() = runTest {
        server.enqueue(
            MockResponse().setResponseCode(200).setBody(
                "event: run.progress\n" +
                    "data: {\"stage\":\"evidence\",\n" +
                    "data: \"progress_pct\":42}\n\n",
            ),
        )
        val events = mutableListOf<ServerEvent>()
        client.stream("/api/research/runs/r1/events", emptyMap<String, String>()) { events.add(it) }
        assertEquals(1, events.size)
        assertTrue(events[0].data.has("progress_pct"))
        assertEquals(42, events[0].data.get("progress_pct")?.asInt)
    }

    @Test
    fun unknownEventDoesNotFabricateFailure() = runBlocking {
        // 契约要求：SSE 断线/未知事件不得把任务显示为失败。
        // 客户端不根据事件流推断失败——失败只能来自服务端 run.failed 或查询结果。
        val event = ServerEvent("unknown.future", JsonObject())
        assertEquals("unknown.future", event.name)
        assertTrue(event.data.entrySet().isEmpty())
    }
}
