package ai.puregamma.android.data.remote

import android.content.Context
import android.net.Uri

class IbkrOAuthCoordinator(
    private val context: Context,
    private val portfolioRepo: ai.puregamma.android.data.repository.PortfolioRepository,
    private val openBrowser: (Uri) -> Unit,
) {
    suspend fun startOAuth(redirectUri: String): Result<Unit> {
        return runCatching {
            val authUrl = portfolioRepo.ibkrOAuthStart(redirectUri)
            openBrowser(Uri.parse(authUrl))
        }
    }

    suspend fun handleCallback(code: String): Result<Unit> {
        return runCatching {
            portfolioRepo.ibkrOAuthComplete(code)
        }
    }
}
