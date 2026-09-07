import Foundation
import CryptoKit

/// Errores del cliente que la interfaz necesita distinguir.
public enum SeismikAPIError: LocalizedError {
    /// APNs todavía no entregó el token del dispositivo.
    case pushTokenUnavailable
    /// El servidor rechazó la petición.
    case rejected(status: Int, message: String)
    case malformedResponse

    /// 408 y 429 son transitorios; el resto de los 4xx indica un contrato
    /// inválido y reintentarlo sólo repetiría el rechazo.
    public var isPermanent: Bool {
        switch self {
        case .pushTokenUnavailable:
            return false
        case .malformedResponse:
            return true
        case let .rejected(status, _):
            return (400..<500).contains(status) && status != 408 && status != 429
        }
    }

    public var errorDescription: String? {
        switch self {
        case .pushTokenUnavailable:
            return "El token de notificaciones todavía no está disponible."
        case let .rejected(status, message):
            return "El servidor respondió \(status): \(message)"
        case .malformedResponse:
            return "La respuesta del servidor no tiene el formato esperado."
        }
    }
}

/// Resultado de enviar un reporte ciudadano.
public enum ReportSubmission: Equatable {
    case sent(duplicate: Bool)
    /// Sin red: quedó guardado y se reenviará solo.
    case queued
}

/// Cliente de red nativo en Swift con async/await para la API de Seismik.
/// Maneja autenticación segura de sesión en Keychain, registro de dispositivo,
/// firma criptográfica HMAC de reportes y persistencia local de contingencia.
public final class SeismikAPIClient {
    public static let shared = SeismikAPIClient()

    private let baseURL: URL
    private let session: URLSession
    private let keychain = KeychainStore.shared
    private let queue = OfflineReportQueue.shared
    private let encoder = JSONEncoder()

    private static let sessionTokenKey = "seismik.device_session_token"
    private static let crowdTokenKey = "seismik.crowd_token"
    private static let eventCacheKey = "seismik.cached_events_json"
    private static let alertCursorKey = "seismik.alert_cursor"

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

    /// Token APNs del dispositivo, o `nil` mientras Apple no lo entrega.
    ///
    /// Antes se devolvía una cadena de ceros cuando faltaba. Eso registraba el
    /// dispositivo con un destino inexistente: el alta parecía correcta y las
    /// alertas nunca llegaban, sin ningún síntoma visible.
    public var apnsToken: String? {
        let stored = UserDefaults.standard.string(forKey: "seismik.apns_device_token")
        guard let token = stored, !token.isEmpty else { return nil }
        return token
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
        guard let pushToken = apnsToken else {
            throw SeismikAPIError.pushTokenUnavailable
        }
        let url = baseURL.appendingPathComponent("v1/devices/register")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        let registrationPayload: [String: Any] = [
            "device_id": deviceId,
            "platform": "ios",
            "apns_token": pushToken,
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
                return []
            }

            struct StationsResponse: Decodable {
                let stations: [SeismicStation]
            }

            if let decoded = try? JSONDecoder().decode(StationsResponse.self, from: data) {
                return decoded.stations
            }
            return []
        } catch {
            return []
        }
    }

    // MARK: - Reportes Ciudadanos con Firma Criptográfica HMAC

    public var pendingReportCount: Int { queue.pendingCount }

    /// Envía un reporte de sismo sentido; si no hay red, lo guarda para después.
    public func submitFeltReport(_ report: FeltReportPayload) async throws -> ReportSubmission {
        let body = try encoder.encode(report)
        return try await submit(kind: .felt, reportId: report.reportId, body: body)
    }

    /// Envía un reporte de daños; si no hay red, lo guarda para después.
    public func submitDamageReport(_ report: DamageReportPayload) async throws -> ReportSubmission {
        let body = try encoder.encode(report)
        return try await submit(kind: .damage, reportId: report.reportId, body: body)
    }

    /// Reenvía los reportes que quedaron guardados sin conexión.
    @discardableResult
    public func flushPendingReports() async -> QueueFlushResult {
        await queue.flush { [weak self] pending in
            guard let self else { return }
            _ = try await self.deliver(kind: pending.kind, body: pending.body)
        }
    }

    private func submit(
        kind: PendingReportKind,
        reportId: String,
        body: Data
    ) async throws -> ReportSubmission {
        if !isRegistered { _ = try? await registerDevice() }
        do {
            let duplicate = try await deliver(kind: kind, body: body)
            // Aprovecha que hay red para vaciar lo que quedó de intentos previos.
            await flushPendingReports()
            return .sent(duplicate: duplicate)
        } catch let error as SeismikAPIError where error.isPermanent {
            throw error
        } catch {
            // Se guarda el cuerpo exacto: el `report_id` y la hora de
            // observación no cambian, así que el reenvío no crea un duplicado.
            queue.enqueue(PendingReport(reportId: reportId, kind: kind, body: body))
            return .queued
        }
    }

    /// Publica el cuerpo exacto en la API y devuelve si el servidor lo consideró
    /// duplicado. Lanza `SeismikAPIError.rejected` para que la cola distinga un
    /// rechazo definitivo de una caída de red.
    @discardableResult
    private func deliver(kind: PendingReportKind, body: Data) async throws -> Bool {
        let url = baseURL.appendingPathComponent(kind.path)
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpBody = body

        if let secret = crowdToken {
            let timestamp = String(format: "%.3f", Date().timeIntervalSince1970)
            request.setValue(timestamp, forHTTPHeaderField: "X-Seismik-Timestamp")
            request.setValue(
                hmacSha256Hex(secret: secret, timestamp: timestamp, body: body),
                forHTTPHeaderField: "X-Seismik-Signature"
            )
        }
        if let sessionToken = deviceSessionToken {
            request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw SeismikAPIError.malformedResponse
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? ""
            throw SeismikAPIError.rejected(status: httpResponse.statusCode, message: message)
        }
        struct Accepted: Decodable { let duplicate: Bool? }
        return (try? JSONDecoder().decode(Accepted.self, from: data))?.duplicate ?? false
    }

    // MARK: - Alertas recibidas sin conexión

    /// Recupera del servidor las alertas emitidas mientras el teléfono no tuvo
    /// red, con el mismo cursor que usa la app de Android para no repetirlas.
    public func fetchMissedAlerts() async -> [SeismicEvent] {
        guard let sessionToken = deviceSessionToken else { return [] }
        var components = URLComponents(
            url: baseURL.appendingPathComponent("v1/alerts/recent"),
            resolvingAgainstBaseURL: true
        )
        var items = [URLQueryItem(name: "device_id", value: deviceId)]
        if let cursor = UserDefaults.standard.string(forKey: Self.alertCursorKey), !cursor.isEmpty {
            items.append(URLQueryItem(name: "since", value: cursor))
        }
        components?.queryItems = items
        guard let url = components?.url else { return [] }

        var request = URLRequest(url: url)
        request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")

        struct LedgerPage: Decodable {
            let alerts: [SeismicEvent]
            let cursor: String?
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let http = response as? HTTPURLResponse,
                  (200...299).contains(http.statusCode) else {
                // Un 404 significa que el registro se perdió; el próximo alta lo
                // restablece y no hay nada que recuperar entretanto.
                return []
            }
            guard let page = try? JSONDecoder().decode(LedgerPage.self, from: data) else {
                return []
            }
            if let next = page.cursor, !next.isEmpty {
                UserDefaults.standard.set(next, forKey: Self.alertCursorKey)
            }
            return page.alerts
        } catch {
            return []
        }
    }

    // MARK: - Detección colaborativa

    /// Envía un ping de aceleración firmado. Devuelve si el servidor lo aceptó.
    @discardableResult
    public func sendShake(
        latitude: Double,
        longitude: Double,
        pgaG: Double,
        at moment: Date
    ) async -> Bool {
        guard let secret = crowdToken else { return false }
        let milliseconds = Int(moment.timeIntervalSince1970 * 1000)
        let payload: [String: Any] = [
            "device_id": deviceId,
            "lat": latitude,
            "lon": longitude,
            "pga": pgaG,
            "timestamp": milliseconds
        ]
        guard let body = try? JSONSerialization.data(withJSONObject: payload) else { return false }

        var request = URLRequest(url: baseURL.appendingPathComponent("v1/crowd/shake"))
        request.httpMethod = "POST"
        request.httpBody = body
        let timestamp = String(format: "%.3f", Double(milliseconds) / 1000)
        request.setValue(timestamp, forHTTPHeaderField: "X-Seismik-Timestamp")
        request.setValue(
            hmacSha256Hex(secret: secret, timestamp: timestamp, body: body),
            forHTTPHeaderField: "X-Seismik-Signature"
        )
        if let sessionToken = deviceSessionToken {
            request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        guard let (_, response) = try? await session.data(for: request),
              let http = response as? HTTPURLResponse else { return false }
        return (200...299).contains(http.statusCode)
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

    /// Historial guardado de la última sincronización correcta.
    ///
    /// Sin caché devuelve una lista vacía. Nunca datos de ejemplo: en una app de
    /// alerta sísmica, mostrar sismos inventados con el sello de una agencia
    /// oficial es peor que no mostrar nada.
    private func loadCachedEvents() -> [SeismicEvent] {
        guard let cachedData = UserDefaults.standard.data(forKey: Self.eventCacheKey) else {
            return []
        }
        struct EventsResponse: Decodable {
            let events: [SeismicEvent]
        }
        if let decoded = try? JSONDecoder().decode(EventsResponse.self, from: cachedData) {
            return decoded.events
        }
        if let raw = try? JSONDecoder().decode([SeismicEvent].self, from: cachedData) {
            return raw
        }
        return []
    }

}

