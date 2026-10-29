package ai.puregamma.android.agent

import com.google.gson.JsonObject
import com.google.gson.JsonParser
import java.io.File

/** docs/mobile/fixtures: real server responses shared with the iOS tests. */
object ContractFixtures {
    private val directory: File by lazy {
        val configured = System.getProperty("pg.contractFixtures")
        val candidates = listOfNotNull(configured, "../../../docs/mobile/fixtures", "../../docs/mobile/fixtures")
        candidates.map(::File).firstOrNull { it.isDirectory }
            ?: error("contract fixtures not found (pg.contractFixtures=$configured)")
    }

    fun text(name: String): String = File(directory, name).readText()

    /** `status` and `body` of an HTTP fixture. */
    fun http(name: String): Pair<Int, JsonObject> {
        val root = JsonParser.parseString(text(name)).asJsonObject
        return root.get("status").asInt to root.getAsJsonObject("body")
    }

    fun body(name: String): String = http(name).second.toString()
}
