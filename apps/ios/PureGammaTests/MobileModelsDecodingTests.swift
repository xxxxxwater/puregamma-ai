import Foundation
import Testing
@testable import PureGamma

@MainActor struct MobileModelsDecodingTests {
    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try JSONDecoder.pg.decode(T.self, from: Data(json.utf8))
    }

    @Test func capabilitiesDecodeAllFlags() throws {
        let dto = try decode(MobileCapabilitiesDTO.self, """
        {
          "harness_research_enabled": true,
          "memory_service_enabled": true,
          "auto_trading_enabled": false,
          "paper_trading_enabled": false,
          "shadow_trading_enabled": false,
          "live_trading_enabled": false,
          "user_can_start_research": true,
          "user_can_manage_memory": true,
          "user_can_view_trading_mandates": true,
          "user_can_pause_mandates": false,
          "harness_retry_enabled": true,
          "app_min_version": "1.4.0",
          "maintenance_message": null
        }
        """)
        let capabilities = dto.domain
        #expect(capabilities.harnessResearchEnabled)
        #expect(capabilities.userCanPauseMandates == false)
        #expect(capabilities.serverContractAvailable)
        #expect(!capabilities.liveTradingEnabled)
    }

    @Test func capabilitiesTolerateUnknownFields() throws {
        let dto = try decode(MobileCapabilitiesDTO.self, """
        {
          "harness_research_enabled": true,
          "future_field": {"nested": [1,2,3]}
        }
        """)
        #expect(dto.domain.harnessResearchEnabled)
        #expect(dto.domain.memoryServiceEnabled == false)
    }

    @Test func researchRunDecodesEveryServerState() throws {
        for raw in ["queued", "preparing", "running", "validating", "completed", "degraded", "failed", "canceled", "timed_out"] {
            let dto = try decode(ResearchRunEnvelopeDTO.self, """
            {"run": {"id": "r1", "name": "n", "status": "\(raw)", "verification": "verified",
              "created_at": "2026-08-15T02:00:00Z", "updated_at": "2026-08-15T02:11:00Z",
              "credits_used": 3.2, "data_sources": ["market"], "evidence_count": 2, "citation_count": 1}}
            """)
            #expect(dto.run.domain.state.rawValue == raw)
        }
    }

    @Test func researchRunUnknownStateFallsBackToIdle() throws {
        let dto = try decode(ResearchRunEnvelopeDTO.self, #"{"run": {"id": "r1", "name": "n", "status": "brand_new_state"}}"#)
        #expect(dto.run.domain.state == .idle)
    }

    @Test func researchRunDegradedFlagOverridesVerification() throws {
        let dto = try decode(ResearchRunEnvelopeDTO.self, #"{"run": {"id": "r1", "name": "n", "status": "completed", "verification": "verified", "is_degraded": true}}"#)
        #expect(dto.run.domain.effectiveVerification == .degraded)
    }

    @Test func evidenceDecodesVerificationFields() throws {
        let dto = try decode(ResearchEvidenceEnvelopeDTO.self, """
        {"evidence": [{"id": "e1", "run_id": "r1", "provider": "coingecko", "title": "t",
          "url": "https://example.com/x", "source_scope": "market", "is_verified": false,
          "verification_note": "manual review", "citation_index": 3}]}
        """)
        let item = dto.evidence[0].domain
        #expect(item.isVerified == false)
        #expect(item.citationIndex == 3)
        #expect(item.verificationNote == "manual review")
    }

    @Test func memorySettingsDecodeWithDefaults() throws {
        let dto = try decode(MemorySettingsEnvelopeDTO.self, """
        {"settings": {"short_term_enabled": true, "mid_term_enabled": false,
          "conversation_summary_enabled": true, "research_memory_enabled": false,
          "portfolio_memory_enabled": false}}
        """)
        let settings = dto.settings.domain
        #expect(settings.consentRequired)
        #expect(settings.retentionDays == 30)
        #expect(settings.shortTermEnabled)
    }

    @Test func memoryItemLifecycleParsesAllStatuses() throws {
        for raw in ["saved", "pending", "rejected", "expired", "deleted"] {
            let dto = try decode(MemoryItemsEnvelopeDTO.self, """
            {"items": [{"id": "m1", "scope": "mid_term", "kind": "preference",
              "content_preview": "p", "status": "\(raw)"}]}
            """)
            #expect(dto.items[0].domain.lifecycle == MemoryItemLifecycle(serverValue: raw))
        }
    }

    @Test func memoryUnknownStatusFallsBackToSaved() throws {
        let dto = try decode(MemoryItemsEnvelopeDTO.self, #"{"items": [{"id": "m1", "scope": "mid_term", "kind": "k", "content_preview": "p", "status": "???"}]}"#)
        #expect(dto.items[0].domain.lifecycle == .saved)
    }

    @Test func mandateDecodesLiveDisabledEnvironment() throws {
        let dto = try decode(TradingMandateEnvelopeDTO.self, """
        {"mandate": {"id": "m1", "name": "n", "strategy_name": "s", "environment": "live_disabled",
          "paused": true, "risk_block_reason": "daily_loss_limit"}}
        """)
        let mandate = dto.mandate.domain
        #expect(mandate.environment == .liveDisabled)
        #expect(mandate.environment.isLive)
    }

    @Test func riskLimitsDecodeDecimalStrings() throws {
        let dto = try decode(MandateRiskEnvelopeDTO.self, """
        {"risk": {"max_notional": "100000.00000000", "daily_loss_limit": "5000.00000000",
          "max_leverage": "2.0", "max_position_size_pct": "25.0"}}
        """)
        #expect(dto.risk.domain.maxLeverage == Decimal(string: "2.0"))
    }

    @Test func unknownTopLevelFieldsAreIgnored() throws {
        let dto = try decode(MobileCapabilitiesDTO.self, """
        {"harness_research_enabled": false, "whatever": "ignored", "array": [1,2]}
        """)
        #expect(dto.domain.harnessResearchEnabled == false)
    }

    @Test func subscriptionToleratesMissingAndUnknownMembershipTier() throws {
        let missing = try decode(SubscriptionDTO.self, """
        {"plan": "Pro", "subscription_status": "active", "credit_balance": 42,
         "entitlement": {"allowed_data_sources": ["market"]}}
        """)
        #expect(missing.membershipTier == nil)

        let unknown = try decode(SubscriptionDTO.self, """
        {"plan": "Max", "membership_tier": "diamond", "subscription_status": "active",
         "credit_balance": 42, "entitlement": {}}
        """)
        #expect(unknown.membershipTier == "diamond")
        // Unknown tier never crashes and falls back to the raw plan label.
        #expect(MembershipTier.label(unknown.membershipTier, plan: "Max") == "Max")

        let gold = try decode(SubscriptionDTO.self, """
        {"plan": "Max", "membership_tier": "gold", "subscription_status": "active",
         "credit_balance": 42, "entitlement": {}}
        """)
        #expect(MembershipTier.label(gold.membershipTier, plan: "Max") == NSLocalizedString("tier.gold", comment: ""))
    }
}
