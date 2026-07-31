package ai.puregamma.android.data.remote

class RetrofitApiException(val status: Int, override val message: String, val code: String? = null) : Exception(message)
