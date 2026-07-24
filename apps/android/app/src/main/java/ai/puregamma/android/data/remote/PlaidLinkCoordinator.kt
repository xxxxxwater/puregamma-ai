package ai.puregamma.android.data.remote

import android.content.Context
import android.net.Uri
import ai.puregamma.android.MainActivity

class PlaidLinkCoordinator(
    private val context: Context,
    private val portfolioRepo: ai.puregamma.android.data.repository.PortfolioRepository,
    private val openBrowser: (Uri) -> Unit,
) {
    suspend fun startLink(): Result<Unit> {
        return runCatching {
            val linkToken = portfolioRepo.createPlaidLinkToken()
            val plaidUrl = "https://cdn.plaid.com/link/v2/stable/link.html" +
                "?token=$linkToken" +
                "&isMobileWebview=true" +
                "&oauthRedirectUri=puregamma://plaid/callback"
            openBrowser(Uri.parse(plaidUrl))
        }
    }

    suspend fun handleCallback(publicToken: String): Result<Unit> {
        return runCatching {
            portfolioRepo.exchangePlaidToken(publicToken)
        }
    }
}
