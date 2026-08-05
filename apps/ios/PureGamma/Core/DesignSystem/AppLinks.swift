import Foundation

enum AppLinks {
    /// Optional by design: a missing/malformed build-config URL hides the link
    /// instead of crashing on the Sign-in screen. The API base URL keeps its
    /// hard `fatalError` in `APIConfiguration` because a Release build without
    /// an API endpoint is unusable, whereas missing legal links degrade
    /// gracefully to a smaller footer.
    static let privacyPolicy = url(for: "PGPrivacyPolicyURL")
    static let terms = url(for: "PGTermsURL")
    static let support = url(for: "PGSupportURL")

    private static func url(for key: String) -> URL? {
        guard let raw = Bundle.main.object(forInfoDictionaryKey: key) as? String,
              let url = URL(string: raw),
              url.host != nil else { return nil }
        return url
    }
}
