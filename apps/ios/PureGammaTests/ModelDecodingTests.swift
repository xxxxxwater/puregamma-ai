import Foundation
import Testing
@testable import PureGamma

@MainActor struct ModelDecodingTests {
    @Test func accountMoneyDecodesAsDecimal() throws {
        let data = Data(#"{"connected":true,"stale":false,"data_as_of":"2026-07-15T00:00:00+00:00","nav":123456.78,"available_cash":1000.01,"nav_history":[],"connections":[],"providers":{"plaid":true,"ibkr":true,"hyperliquid":true}}"#.utf8)
        let value = try JSONDecoder.pg.decode(PortfolioDTO.self, from: data).domain
        #expect(value.nav == Decimal(string: "123456.78"))
        #expect(value.availableCash == Decimal(string: "1000.01"))
    }

    @Test func UTCDisplaysInDeviceTimeZone() {
        let data = Data("\"2026-07-15T00:00:00Z\"".utf8)
        let utc = try? JSONDecoder.pg.decode(Date.self, from: data)
        #expect(utc != nil)
        #expect(PGFormat.dateTime(utc) != "—")
    }
}
