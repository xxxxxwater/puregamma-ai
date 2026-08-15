package ai.puregamma.android.model

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ResearchRunStateTest {

    @Test
    fun terminalStatesAreCorrect() {
        for (terminal in listOf(
            ResearchRunState.COMPLETED,
            ResearchRunState.DEGRADED,
            ResearchRunState.FAILED,
            ResearchRunState.CANCELED,
            ResearchRunState.TIMED_OUT,
        )) {
            assertTrue("$terminal should be terminal", terminal.isTerminal)
            assertFalse("$terminal should not be active", terminal.isActive)
        }
        for (active in listOf(
            ResearchRunState.QUEUED,
            ResearchRunState.PREPARING,
            ResearchRunState.RUNNING,
            ResearchRunState.VALIDATING,
        )) {
            assertTrue("$active should be active", active.isActive)
            assertFalse("$active should not be terminal", active.isTerminal)
        }
    }

    @Test
    fun retryableStatesAreFailures() {
        assertTrue(ResearchRunState.FAILED.isRetryable)
        assertTrue(ResearchRunState.CANCELED.isRetryable)
        assertTrue(ResearchRunState.TIMED_OUT.isRetryable)
        assertFalse(ResearchRunState.COMPLETED.isRetryable)
        assertFalse(ResearchRunState.DEGRADED.isRetryable)
        assertFalse(ResearchRunState.RUNNING.isRetryable)
        assertFalse(ResearchRunState.IDLE.isRetryable)
        assertFalse(ResearchRunState.SUBMITTING.isRetryable)
    }

    @Test
    fun fromServerMapsContractValues() {
        assertTrue(ResearchRunState.fromServer("queued") == ResearchRunState.QUEUED)
        assertTrue(ResearchRunState.fromServer("TIMED_OUT") == ResearchRunState.TIMED_OUT)
        assertTrue(ResearchRunState.fromServer("timed_out") == ResearchRunState.TIMED_OUT)
        assertTrue(ResearchRunState.fromServer("unknown") == ResearchRunState.IDLE)
        assertTrue(ResearchRunState.fromServer(null) == ResearchRunState.IDLE)
    }

    @Test
    fun environmentCanNeverBeLiveActionable() {
        // LIVE 即使所有 Flag 都开也不得操作（客户端硬约束，与测试无关的部署状态同理）。
        val allOn = MobileCapabilities(
            harnessResearchEnabled = true,
            autoTradingEnabled = true,
            paperTradingEnabled = true,
            shadowTradingEnabled = true,
            liveTradingEnabled = true,
            userCanPauseMandates = true,
            serverContractAvailable = true,
        )
        assertFalse(MandateActionPolicy.pauseAllowed(TradingEnvironment.LIVE_DISABLED, paused = false, capabilities = allOn))
        assertFalse(MandateActionPolicy.resumeAllowed(TradingEnvironment.LIVE_DISABLED, paused = true, capabilities = allOn))
        assertFalse(MandateActionPolicy.liveActionAllowed(TradingEnvironment.LIVE_DISABLED))
        assertTrue(TradingEnvironment.LIVE_DISABLED.isLive)
        assertFalse(TradingEnvironment.LIVE_DISABLED.canBePausedOrResumed)
    }

    @Test
    fun pauseResumeOnlyForPaperAndShadowWithCapability() {
        val capabilities = MobileCapabilities(
            autoTradingEnabled = true,
            userCanPauseMandates = true,
            serverContractAvailable = true,
        )
        assertTrue(MandateActionPolicy.pauseAllowed(TradingEnvironment.PAPER, paused = false, capabilities = capabilities))
        assertTrue(MandateActionPolicy.pauseAllowed(TradingEnvironment.SHADOW, paused = false, capabilities = capabilities))
        assertFalse(MandateActionPolicy.pauseAllowed(TradingEnvironment.OFF, paused = false, capabilities = capabilities))
        assertFalse(MandateActionPolicy.pauseAllowed(TradingEnvironment.PAPER, paused = true, capabilities = capabilities))
        assertFalse(MandateActionPolicy.resumeAllowed(TradingEnvironment.PAPER, paused = false, capabilities = capabilities))
        assertTrue(MandateActionPolicy.resumeAllowed(TradingEnvironment.PAPER, paused = true, capabilities = capabilities))
    }

    @Test
    fun pauseRequiresServerCapability() {
        val noPermission = MobileCapabilities(autoTradingEnabled = true, userCanPauseMandates = false, serverContractAvailable = true)
        assertFalse(MandateActionPolicy.pauseAllowed(TradingEnvironment.PAPER, paused = false, capabilities = noPermission))
        val autoOff = MobileCapabilities(autoTradingEnabled = false, userCanPauseMandates = true, serverContractAvailable = true)
        assertFalse(MandateActionPolicy.pauseAllowed(TradingEnvironment.PAPER, paused = false, capabilities = autoOff))
    }
}
