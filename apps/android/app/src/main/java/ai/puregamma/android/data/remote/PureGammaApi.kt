package ai.puregamma.android.data.remote

import ai.puregamma.android.data.remote.dto.*
import retrofit2.Response
import retrofit2.http.*

interface PureGammaApi {

    @GET("/me")
    suspend fun getUser(): UserEnvelopeDto

    @POST("/auth/mobile/email/login")
    suspend fun emailLogin(@Body body: EmailLoginRequest): AuthResponseDto

    @POST("/auth/mobile/email/register")
    suspend fun emailRegister(@Body body: EmailRegisterRequest): AuthResponseDto

    @POST("/auth/mobile/google/start")
    suspend fun googleOAuthStart(@Body body: GoogleOAuthStartRequest): GoogleOAuthStartResponseDto

    @POST("/auth/mobile/google/exchange")
    suspend fun googleOAuthExchange(@Body body: GoogleOAuthExchangeRequest): AuthResponseDto

    @POST("/auth/logout")
    suspend fun logout(): Response<Void>

    @DELETE("/me")
    suspend fun deleteAccount(): Response<Void>

    @GET("/market/snapshot")
    suspend fun getMarketSnapshot(): MarketEnvelopeDto

    @GET("/reports")
    suspend fun getReports(): ReportsEnvelopeDto

    @GET("/billing/subscription")
    suspend fun getSubscription(): SubscriptionDto

    @GET("/portfolio")
    suspend fun getPortfolio(): PortfolioDto

    @POST("/portfolio")
    suspend fun updatePortfolio(@Body body: Map<String, String>): PortfolioDto

    @GET("/portfolio/autopilot")
    suspend fun getAutopilot(): AutopilotDto

    @POST("/portfolio/autopilot/run")
    suspend fun runAutopilotReview(): AutopilotDto

    @POST("/portfolio/hyperliquid/connect")
    suspend fun connectHyperliquid(@Body body: Map<String, String>): PortfolioDto

    @POST("/portfolio/accounts/{id}/sync")
    suspend fun syncConnection(@Path("id") id: String): PortfolioDto

    @DELETE("/portfolio/accounts/{id}")
    suspend fun deleteConnection(@Path("id") id: String): Response<Void>

    @POST("/portfolio/plaid/link-token")
    suspend fun createPlaidLinkToken(@Body body: Map<String, String>): PlaidLinkTokenDto

    @POST("/portfolio/plaid/exchange")
    suspend fun exchangePlaidToken(@Body body: Map<String, String>): PortfolioDto

    @POST("/portfolio/ibkr/mobile/start")
    suspend fun ibkrOAuthStart(@Body body: IbkrOAuthStartRequest): IbkrOAuthStartResponseDto

    @POST("/portfolio/ibkr/mobile/complete")
    suspend fun ibkrOAuthComplete(@Body body: IbkrOAuthCompleteRequest): PortfolioDto

    @GET("/api/agent/conversations")
    suspend fun getConversations(): ConversationsEnvelopeDto

    @POST("/api/agent/conversations")
    suspend fun createConversation(@Body body: Map<String, String?>): ConversationEnvelopeDto

    @GET("/api/agent/conversations/{id}")
    suspend fun getConversation(@Path("id") id: String): ConversationDetailDto

    @PATCH("/api/agent/conversations/{id}")
    suspend fun updateConversation(
        @Path("id") id: String,
        @Body body: ConversationPatchRequest,
    ): ConversationEnvelopeDto

    @DELETE("/api/agent/conversations/{id}")
    suspend fun deleteConversation(@Path("id") id: String): Response<Void>

    @GET("/api/agent/capabilities")
    suspend fun getCapabilities(): CapabilitiesEnvelopeDto

    @POST("/api/agent/runs/{id}/cancel")
    suspend fun cancelRun(@Path("id") id: String): Response<Void>

    @GET("/options/long-gamma")
    suspend fun getLongGamma(@Query("currency") currency: String): LongGammaEnvelopeDto

    @GET("/notifications/preferences/daily-brief")
    suspend fun getDailyPushPreferences(): DailyPushEnvelopeDto

    @PUT("/notifications/preferences/daily-brief")
    suspend fun updateDailyPushPreferences(@Body body: DailyPushDto): DailyPushEnvelopeDto

    @POST("/notifications/devices")
    suspend fun registerPushDevice(@Body body: PushDeviceRequestDto): PushDeviceRegistrationDto

    @POST("/notifications/devices/unregister")
    suspend fun unregisterPushDevice(@Body body: Map<String, String>): Response<Void>
}
