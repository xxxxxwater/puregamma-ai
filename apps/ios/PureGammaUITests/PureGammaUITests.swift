import XCTest

@MainActor final class PureGammaUITests: XCTestCase {
    func testLoginIsAccessibleAtLargeDynamicType() {
        let app = XCUIApplication()
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityExtraExtraLarge"]
        app.launch()
        XCTAssertTrue(app.buttons["apple-sign-in"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["google-sign-in"].exists)
        XCTAssertTrue(app.staticTexts["PUREGAMMA AI"].exists)
    }
}
