import Foundation
import Security

protocol TokenStoring: Sendable { func read() -> String?; func save(_ token: String) throws; func delete() }

struct KeychainTokenStore: TokenStoring {
    private let service: String
    private let account: String

    init(service: String = "ai.puregamma.ios.auth", account: String = "bearer-token") {
        self.service = service; self.account = account
    }

    private var baseQuery: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: account, kSecUseDataProtectionKeychain as String: true]
    }

    func read() -> String? {
        var query = baseQuery
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return String(data: data, encoding: .utf8)
    }

    func save(_ token: String) throws {
        delete()
        var attributes = baseQuery
        attributes[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
        attributes[kSecValueData as String] = Data(token.utf8)
        let status = SecItemAdd(attributes as CFDictionary, nil)
        guard status == errSecSuccess else { throw APIError.server(status: Int(status), message: "Keychain write failed") }
    }
    func delete() { SecItemDelete(baseQuery as CFDictionary) }
}
