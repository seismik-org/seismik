import Foundation
import Security

/// Minimal Keychain wrapper for credentials issued to this app installation.
///
/// Device sessions and report-signing tokens are bearer secrets. Keeping them
/// out of `UserDefaults` prevents them from being copied in plain text as part
/// of the preferences domain. Values are device-only and become available
/// after the first unlock so background notification work can still run.
public final class KeychainStore {
    public static let shared = KeychainStore()

    private let service: String

    public init(service: String = Bundle.main.bundleIdentifier ?? "org.seismik.ios") {
        self.service = service
    }

    public func string(for account: String) throws -> String? {
        var query = baseQuery(account: account)
        query[kSecReturnData as String] = true
        query[kSecMatchLimit as String] = kSecMatchLimitOne

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        if status == errSecItemNotFound {
            return nil
        }
        guard status == errSecSuccess else {
            throw KeychainStoreError.unexpectedStatus(status)
        }
        guard let data = item as? Data,
              let value = String(data: data, encoding: .utf8) else {
            throw KeychainStoreError.invalidStoredValue
        }
        return value
    }

    public func set(_ value: String, for account: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainStoreError.invalidStoredValue
        }

        let query = baseQuery(account: account)
        let attributes: [String: Any] = [
            kSecValueData as String: data,
            kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
        ]
        let updateStatus = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if updateStatus == errSecSuccess {
            return
        }
        guard updateStatus == errSecItemNotFound else {
            throw KeychainStoreError.unexpectedStatus(updateStatus)
        }

        var newItem = query
        attributes.forEach { newItem[$0.key] = $0.value }
        let addStatus = SecItemAdd(newItem as CFDictionary, nil)
        guard addStatus == errSecSuccess else {
            throw KeychainStoreError.unexpectedStatus(addStatus)
        }
    }

    public func remove(_ account: String) throws {
        let status = SecItemDelete(baseQuery(account: account) as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw KeychainStoreError.unexpectedStatus(status)
        }
    }

    private func baseQuery(account: String) -> [String: Any] {
        [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecAttrSynchronizable as String: kCFBooleanFalse as Any,
        ]
    }
}

public enum KeychainStoreError: LocalizedError {
    case invalidStoredValue
    case unexpectedStatus(OSStatus)

    public var errorDescription: String? {
        switch self {
        case .invalidStoredValue:
            return "No se pudo leer una credencial segura del dispositivo."
        case .unexpectedStatus(let status):
            let systemMessage = SecCopyErrorMessageString(status, nil) as String?
            return systemMessage.map { "Keychain: \($0)" } ?? "Keychain devolvió el código \(status)."
        }
    }
}
