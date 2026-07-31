import Foundation

enum AppLinks {
    static let privacyPolicy = requiredURL(for: "PGPrivacyPolicyURL")
    static let terms = requiredURL(for: "PGTermsURL")
    static let support = requiredURL(for: "PGSupportURL")

    private static func requiredURL(for key: String) -> URL {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: key) as? String,
              let url = URL(string: raw) else {
            fatalError("Missing required URL configuration: \(key)")
        }
        return url
    }
}
