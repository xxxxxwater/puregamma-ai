import Foundation

struct APIConfiguration: Sendable {
    let baseURL: URL
    let environment: String
    let callbackScheme = "puregamma"
    let callbackURL = "puregamma://oauth/callback"
    let portfolioCallbackURL = "puregamma://oauth/ibkr"

    static var current: APIConfiguration {
        let info = Bundle.main.infoDictionary ?? [:]
        let environment = info["PGEnvironment"] as? String ?? "production"
        let configured = info["PGAPIBaseURL"] as? String
        let debugOverride = environment == "development" ? ProcessInfo.processInfo.environment["PUREGAMMA_API_BASE_URL"] : nil
        guard let raw = debugOverride ?? configured,
              let url = URL(string: raw),
              url.host != nil else {
            fatalError("PGAPIBaseURL is missing or invalid")
        }
        if environment == "production" && url.scheme != "https" {
            fatalError("Production API must use HTTPS")
        }
        return APIConfiguration(baseURL: url, environment: environment)
    }
}
