import CryptoKit
import Foundation

enum PKCE {
    static func random(byteCount: Int = 32) -> String {
        Data((0..<byteCount).map { _ in UInt8.random(in: .min ... .max) }).base64URLEncodedString()
    }
    static func challenge(for verifier: String) -> String { Data(SHA256.hash(data: Data(verifier.utf8))).base64URLEncodedString() }
    static func appleNonce(for nonce: String) -> String { SHA256.hash(data: Data(nonce.utf8)).map { String(format: "%02x", $0) }.joined() }
}
private extension Data {
    func base64URLEncodedString() -> String { base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
}
