import Foundation
import Testing
@testable import PureGamma

@MainActor struct TradingSafetyPolicyTests {
    private var capabilities: MobileCapabilities {
        var value = MobileCapabilities()
        value.serverContractAvailable = true
        value.autoTradingEnabled = true
        value.userCanViewTradingMandates = true
        value.userCanPauseMandates = true
        return value
    }

    @Test func liveIsNeverActionableEvenWhenEveryFlagIsOn() {
        var allOn = capabilities
        allOn.paperTradingEnabled = true
        allOn.shadowTradingEnabled = true
        allOn.liveTradingEnabled = true
        allOn.userCanPauseMandates = true
        // LIVE 即使环境变量、部署标记、本地配置全部开启也不得操作。
        #expect(!MandateActionPolicy.pauseAllowed(environment: .liveDisabled, paused: false, capabilities: allOn))
        #expect(!MandateActionPolicy.resumeAllowed(environment: .liveDisabled, paused: true, capabilities: allOn))
        #expect(!MandateActionPolicy.liveActionAllowed(environment: .liveDisabled))
    }

    @Test func pauseOnlyForPaperAndShadow() {
        #expect(MandateActionPolicy.pauseAllowed(environment: .paper, paused: false, capabilities: capabilities))
        #expect(MandateActionPolicy.pauseAllowed(environment: .shadow, paused: false, capabilities: capabilities))
        #expect(!MandateActionPolicy.pauseAllowed(environment: .off, paused: false, capabilities: capabilities))
        #expect(!MandateActionPolicy.pauseAllowed(environment: .unavailable, paused: false, capabilities: capabilities))
    }

    @Test func resumeRequiresPausedState() {
        #expect(MandateActionPolicy.resumeAllowed(environment: .paper, paused: true, capabilities: capabilities))
        #expect(!MandateActionPolicy.resumeAllowed(environment: .paper, paused: false, capabilities: capabilities))
    }

    @Test func actionsRequireServerCapability() {
        var disabled = capabilities
        disabled.userCanPauseMandates = false
        #expect(!MandateActionPolicy.pauseAllowed(environment: .paper, paused: false, capabilities: disabled))
        var autoOff = capabilities
        autoOff.autoTradingEnabled = false
        #expect(!MandateActionPolicy.resumeAllowed(environment: .shadow, paused: true, capabilities: autoOff))
    }

    @Test func defaultCapabilitiesAreAllOff() {
        let none = MobileCapabilities.unavailable
        #expect(!none.harnessResearchEnabled)
        #expect(!none.memoryServiceEnabled)
        #expect(!none.autoTradingEnabled)
        #expect(!none.paperTradingEnabled)
        #expect(!none.shadowTradingEnabled)
        #expect(!none.liveTradingEnabled)
        #expect(!none.serverContractAvailable)
    }

    @Test func environmentParsingCoversContractValues() {
        #expect(TradingEnvironment(rawValue: "off") == .off)
        #expect(TradingEnvironment(rawValue: "paper") == .paper)
        #expect(TradingEnvironment(rawValue: "shadow") == .shadow)
        #expect(TradingEnvironment(rawValue: "live_disabled") == .liveDisabled)
        #expect(TradingEnvironment(rawValue: "live") == nil)
    }
}

@MainActor struct MemoryConsentTests {
    @Test func consentRequiredDominatesUntilGranted() {
        let settings = MemorySettings(shortTermEnabled: true, midTermEnabled: false, conversationSummaryEnabled: false, researchMemoryEnabled: false, portfolioMemoryEnabled: false, consentRequired: true, retentionDays: 30)
        #expect(MemoryState.state(settings: settings, consentGranted: false) == .consentRequired)
        #expect(MemoryState.state(settings: settings, consentGranted: true) == .enabled)
    }

    @Test func disabledWhenEverythingIsOff() {
        let settings = MemorySettings.allOff
        #expect(MemoryState.state(settings: settings, consentGranted: true) == .disabled)
    }

    @Test func neverStoredCategoriesCoverSecrets() {
        let categories = Set(MemorySettings.neverStoredCategories)
        for forbidden in ["private_keys", "api_secrets", "card_details", "auth_tokens", "account_credentials", "unconfirmed_trade_intent", "unverified_harness_inference", "auto_trade_orders"] {
            #expect(categories.contains(forbidden))
        }
    }

    @Test func endpointMissingErrorIsDetected() {
        #expect(APIError.server(status: 404, message: "not found").isEndpointMissing)
        #expect(APIError.server(status: 501, message: "not implemented").isEndpointMissing)
        #expect(!APIError.server(status: 500, message: "boom").isEndpointMissing)
        #expect(!APIError.unauthorized.isEndpointMissing)
    }
}
