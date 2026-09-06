import Foundation
import CryptoKit

/// Cliente de red nativo en Swift con async/await para la API de Seismik.
/// Maneja autenticación segura de sesión en Keychain, registro de dispositivo,
/// firma criptográfica HMAC de reportes y persistencia local de contingencia.
public final class SeismikAPIClient {
    public static let shared = SeismikAPIClient()

    private let baseURL: URL
    private let session: URLSession
    private let keychain = KeychainStore.shared

    private static let sessionTokenKey = "seismik.device_session_token"
    private static let crowdTokenKey = "seismik.crowd_token"
    private static let eventCacheKey = "seismik.cached_events_json"

    private init() {
        self.baseURL = URL(string: "https://api.seismik.org")!
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 12.0
        config.timeoutIntervalForResource = 30.0
        config.httpAdditionalHeaders = [
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Seismik-iOS-Native/1.0.0"
        ]
        self.session = URLSession(configuration: config)
    }

    /// Identificador único y persistente de la instalación del dispositivo.
    public var deviceId: String {
        let key = "seismik.device_id"
        if let existing = UserDefaults.standard.string(forKey: key), !existing.isEmpty {
            return existing
        }
        let newId = UUID().uuidString
        UserDefaults.standard.set(newId, forKey: key)
        return newId
    }

    /// Token de sesión activa en Keychain.
    public var deviceSessionToken: String? {
        try? keychain.string(for: Self.sessionTokenKey)
    }

    /// Token secreto crowd para firma HMAC de reportes sísmicos.
    public var crowdToken: String? {
        try? keychain.string(for: Self.crowdTokenKey)
    }

    /// Indica si el dispositivo cuenta con credenciales válidas registradas.
    public var isRegistered: Bool {
        guard let token = deviceSessionToken, !token.isEmpty else { return false }
        return true
    }

    // MARK: - Registro del Dispositivo

    /// Registra la instalación en el backend Seismik y guarda los tokens en Keychain.
    @discardableResult
    public func registerDevice(
        latitude: Double = 4.65,
        longitude: Double = -74.05,
        countryCode: String = "CO",
        receiveEarlyAlerts: Bool = true,
        receiveOfficialUpdates: Bool = true,
        minimumNotificationMagnitude: Double = 4.0,
        alertRadiusKm: Double = 250.0
    ) async throws -> Bool {
        let url = baseURL.appendingPathComponent("v1/devices/register")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let registrationPayload: [String: Any] = [
            "device_id": deviceId,
            "platform": "ios",
            "apns_token": "0000000000000000000000000000000000000000000000000000000000000000",
            "country_code": countryCode.uppercased(),
            "latitude": latitude,
            "longitude": longitude,
            "critical_alerts_authorized": false,
            "receive_early_alerts": receiveEarlyAlerts,
            "receive_official_updates": receiveOfficialUpdates,
            "minimum_notification_magnitude": minimumNotificationMagnitude,
            "alert_radius_km": alertRadiusKm,
            "locale": Locale.current.identifier.prefix(16),
            "app_attest_token": "seismik-beta-sideload-unverified"
        ]

        request.httpBody = try JSONSerialization.data(withJSONObject: registrationPayload)

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
                return false
            }

            struct RegisterResponse: Decodable {
                let device_id: String
                let registered: Bool
                let crowd_token: String
                let device_session_token: String
            }

            let decoded = try JSONDecoder().decode(RegisterResponse.self, from: data)
            try keychain.set(decoded.device_session_token, for: Self.sessionTokenKey)
            try keychain.set(decoded.crowd_token, for: Self.crowdTokenKey)
            return true
        } catch {
            return false
        }
    }

    // MARK: - Eventos Sísmicos

    /// Obtiene el historial de sismos recientes con soporte para autorización de sesión, reintento y caché offline.
    public func fetchRecentEvents(
        sources: [String] = ["sgc_colombia", "usgs_global"],
        days: Int = 15,
        minimumMagnitude: Double = 2.5
    ) async throws -> [SeismicEvent] {
        if !isRegistered {
            _ = try? await registerDevice()
        }

        var components = URLComponents(url: baseURL.appendingPathComponent("v1/events/history"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "sources", value: sources.sorted().joined(separator: ",")),
            URLQueryItem(name: "days", value: "\(days)"),
            URLQueryItem(name: "minimum_magnitude", value: String(format: "%.1f", minimumMagnitude)),
            URLQueryItem(name: "limit", value: "200")
        ]

        guard let url = components?.url else {
            return loadCachedEvents()
        }

        var request = URLRequest(url: url)
        if let sessionToken = deviceSessionToken {
            request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        do {
            let (data, response) = try await session.data(for: request)
            if let httpResponse = response as? HTTPURLResponse {
                // Si la sesión expiró o es inválida, refrescar registro y reintentar una vez
                if httpResponse.statusCode == 401 {
                    try? keychain.remove(Self.sessionTokenKey)
                    let registered = try await registerDevice()
                    if registered, let freshToken = deviceSessionToken {
                        request.setValue(freshToken, forHTTPHeaderField: "X-Seismik-Device-Session")
                        let (retryData, retryResponse) = try await session.data(for: request)
                        if let retryHttp = retryResponse as? HTTPURLResponse, (200...299).contains(retryHttp.statusCode) {
                            return parseAndCacheEvents(retryData)
                        }
                    }
                }
                guard (200...299).contains(httpResponse.statusCode) else {
                    return loadCachedEvents()
                }
            }

            return parseAndCacheEvents(data)
        } catch {
            return loadCachedEvents()
        }
    }

    // MARK: - Estaciones Sismológicas

    /// Obtiene el listado de estaciones sismológicas activas de la red.
    public func fetchStations() async throws -> [SeismicStation] {
        let url = baseURL.appendingPathComponent("v1/network/stations")
        var request = URLRequest(url: url)
        if let sessionToken = deviceSessionToken {
            request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
                return defaultStations()
            }

            struct StationsResponse: Decodable {
                let stations: [SeismicStation]
            }

            if let decoded = try? JSONDecoder().decode(StationsResponse.self, from: data) {
                return decoded.stations
            }
            return defaultStations()
        } catch {
            return defaultStations()
        }
    }

    // MARK: - Reportes Ciudadanos con Firma Criptográfica HMAC

    /// Envía un reporte de sismo sentido (DYFI) firmado con el secreto del dispositivo.
    public func submitFeltReport(_ report: FeltReportPayload) async throws -> Bool {
        if !isRegistered {
            _ = try? await registerDevice()
        }

        let url = baseURL.appendingPathComponent("v1/reports/felt")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let body = try JSONEncoder().encode(report)
        request.httpBody = body

        if let secret = crowdToken {
            let timestamp = String(format: "%.3f", Date().timeIntervalSince1970)
            let signature = hmacSha256Hex(secret: secret, timestamp: timestamp, body: body)
            request.setValue(timestamp, forHTTPHeaderField: "X-Seismik-Timestamp")
            request.setValue(signature, forHTTPHeaderField: "X-Seismik-Signature")
        }
        if let session = deviceSessionToken {
            request.setValue(session, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { return false }
        return (200...299).contains(httpResponse.statusCode)
    }

    /// Envía un reporte de daños estructurales firmado con el secreto del dispositivo.
    public func submitDamageReport(_ report: DamageReportPayload) async throws -> Bool {
        if !isRegistered {
            _ = try? await registerDevice()
        }

        let url = baseURL.appendingPathComponent("v1/reports/damage")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        let body = try JSONEncoder().encode(report)
        request.httpBody = body

        if let secret = crowdToken {
            let timestamp = String(format: "%.3f", Date().timeIntervalSince1970)
            let signature = hmacSha256Hex(secret: secret, timestamp: timestamp, body: body)
            request.setValue(timestamp, forHTTPHeaderField: "X-Seismik-Timestamp")
            request.setValue(signature, forHTTPHeaderField: "X-Seismik-Signature")
        }
        if let session = deviceSessionToken {
            request.setValue(session, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { return false }
        return (200...299).contains(httpResponse.statusCode)
    }

    // MARK: - Auxiliares Criptográficos y de Caché

    private func hmacSha256Hex(secret: String, timestamp: String, body: Data) -> String {
        let key = SymmetricKey(data: Data(secret.utf8))
        var message = Data(timestamp.utf8)
        message.append(contentsOf: [0x2E]) // "."
        message.append(body)
        let signature = HMAC<SHA256>.authenticationCode(for: message, using: key)
        return signature.map { String(format: "%02x", $0) }.joined()
    }

    private func parseAndCacheEvents(_ data: Data) -> [SeismicEvent] {
        struct EventsResponse: Decodable {
            let events: [SeismicEvent]
        }

        var results: [SeismicEvent] = []
        if let decoded = try? JSONDecoder().decode(EventsResponse.self, from: data) {
            results = decoded.events
        } else if let raw = try? JSONDecoder().decode([SeismicEvent].self, from: data) {
            results = raw
        }

        if !results.isEmpty {
            UserDefaults.standard.set(data, forKey: Self.eventCacheKey)
            return results
        }
        return loadCachedEvents()
    }

    private func loadCachedEvents() -> [SeismicEvent] {
        if let cachedData = UserDefaults.standard.data(forKey: Self.eventCacheKey) {
            struct EventsResponse: Decodable {
                let events: [SeismicEvent]
            }
            if let decoded = try? JSONDecoder().decode(EventsResponse.self, from: cachedData), !decoded.events.isEmpty {
                return decoded.events
            }
            if let raw = try? JSONDecoder().decode([SeismicEvent].self, from: cachedData), !raw.isEmpty {
                return raw
            }
        }
        return SeismicEvent.sampleEvents
    }

    private func defaultStations() -> [SeismicStation] {
        [
            SeismicStation(network: "CM", stationCode: "ROSC", latitude: 4.83, longitude: -74.02),
            SeismicStation(network: "CM", stationCode: "PRA", latitude: 5.06, longitude: -73.34),
            SeismicStation(network: "CM", stationCode: "CAP2", latitude: 4.43, longitude: -73.74),
            SeismicStation(network: "CM", stationCode: "BAR2", latitude: 6.64, longitude: -73.23),
            SeismicStation(network: "CM", stationCode: "SGC1", latitude: 4.64, longitude: -74.08)
        ]
    }
}

