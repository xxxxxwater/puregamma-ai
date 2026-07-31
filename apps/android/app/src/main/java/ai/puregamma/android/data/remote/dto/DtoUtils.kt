package ai.puregamma.android.data.remote.dto

fun Map<String, *>.toNullableStringMap(): Map<String, String?> {
    return mapValues { (_, v) -> v?.toString() }
}
