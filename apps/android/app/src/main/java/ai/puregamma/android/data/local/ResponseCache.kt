package ai.puregamma.android.data.local

import android.content.Context
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.security.MessageDigest
import java.time.Instant

class ResponseCache(context: Context) {
    private val cacheDir = File(context.cacheDir, "pg_api_cache").apply { mkdirs() }
    private val gson = Gson()
    private val metaDir = File(cacheDir, "meta").apply { mkdirs() }

    suspend fun <T> save(value: T, key: String, typeToken: TypeToken<T>) = withContext(Dispatchers.IO) {
        val hashKey = sha256(key)
        val dataFile = File(cacheDir, hashKey)
        val metaFile = File(metaDir, hashKey)
        dataFile.writeText(gson.toJson(value))
        metaFile.writeText(Instant.now().toString())
    }

    suspend fun <T> load(key: String, maxAgeSeconds: Long, typeToken: TypeToken<T>): Pair<T, Instant>? =
        withContext(Dispatchers.IO) {
            val hashKey = sha256(key)
            val dataFile = File(cacheDir, hashKey)
            val metaFile = File(metaDir, hashKey)
            if (!dataFile.exists() || !metaFile.exists()) return@withContext null
            val cachedAt = runCatching { Instant.parse(metaFile.readText().trim()) }.getOrNull() ?: return@withContext null
            val age = java.time.Duration.between(cachedAt, Instant.now()).seconds
            if (age > maxAgeSeconds) return@withContext null
            val data = runCatching { gson.fromJson<T>(dataFile.readText(), typeToken.type) }.getOrNull()
            data?.let { Pair(it, cachedAt) }
        }

    suspend fun loadStaleOrNull(key: String, typeToken: TypeToken<*>): Any? = withContext(Dispatchers.IO) {
        val hashKey = sha256(key)
        val dataFile = File(cacheDir, hashKey)
        if (!dataFile.exists()) return@withContext null
        runCatching { gson.fromJson<Any>(dataFile.readText(), typeToken.type) }.getOrNull()
    }

    suspend fun getCachedAge(key: String): Instant? = withContext(Dispatchers.IO) {
        val metaFile = File(metaDir, sha256(key))
        if (!metaFile.exists()) return@withContext null
        runCatching { Instant.parse(metaFile.readText().trim()) }.getOrNull()
    }

    suspend fun clear() = withContext(Dispatchers.IO) {
        cacheDir.deleteRecursively()
        cacheDir.mkdirs()
        metaDir.mkdirs()
    }

    private fun sha256(input: String): String {
        val bytes = MessageDigest.getInstance("SHA-256").digest(input.toByteArray())
        return bytes.joinToString("") { "%02x".format(it) }
    }
}
