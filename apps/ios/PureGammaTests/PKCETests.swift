import Testing
@testable import PureGamma

@MainActor struct PKCETests {
    @Test func challengeMatchesRFC7636Vector() {
        let verifier = "dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"
        #expect(PKCE.challenge(for: verifier) == "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM")
    }

    @Test func appleNonceUsesLowercaseSHA256Hex() {
        #expect(PKCE.appleNonce(for: "nonce") == "78377b525757b494427f89014f97d79928f3938d14eb51e20fb5dec9834eb304")
    }
}
