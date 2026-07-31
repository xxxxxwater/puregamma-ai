package ai.puregamma.android.data.repository

import ai.puregamma.android.data.remote.dto.*
import org.junit.Assert.*
import org.junit.Test

class SseParserTest {

    @Test
    fun parseSimpleDelta() {
        val json = """{"delta":"Hello"}"""
        val event = json.toTestEvent("message.delta")
        assertEquals("message.delta", event.name)
        assertEquals("Hello", event.data.get("delta")?.asString)
    }

    @Test
    fun parseRunStarted() {
        val json = """{"run_id":"abc123"}"""
        val event = json.toTestEvent("run.started")
        assertEquals("abc123", event.data.get("run_id")?.asString)
    }

    @Test
    fun parseCitation() {
        val json = """{"index":1,"provider":"news","title":"Sample","url":"https://example.com"}"""
        val event = json.toTestEvent("citation")
        assertEquals(1, event.data.get("index")?.asInt)
        assertEquals("news", event.data.get("provider")?.asString)
        assertEquals("Sample", event.data.get("title")?.asString)
    }

    @Test
    fun parseFailedEvent() {
        val json = """{"message":"API error","code":"RATE_LIMITED"}"""
        val event = json.toTestEvent("run.failed")
        assertEquals("API error", event.data.get("message")?.asString)
    }
}

private fun String.toTestEvent(name: String): ai.puregamma.android.data.remote.ServerEvent {
    return ai.puregamma.android.data.remote.ServerEvent(
        name = name,
        data = com.google.gson.JsonParser.parseString(this).asJsonObject,
    )
}
