import Foundation
import CryptoKit
import FirebaseAppCheck
import AuthenticationServices
import UIKit

public struct SeismikAccount: Codable, Equatable {
    public let uid: String
    public let email: String
    public let name: String
}

/// Inicio de sesión web seguro: el proveedor nunca entrega sus tokens a la
/// app. `auth.seismik.org` devuelve un código de un solo uso al esquema propio.
@MainActor
public final class SeismikOAuthSignIn: NSObject, ASWebAuthenticationPresentationContextProviding {
    public static let shared = SeismikOAuthSignIn()
    private var session: ASWebAuthenticationSession?

    public func start(
        provider: String,
        completion: @escaping (Result<SeismikAccount, Error>) -> Void
    ) {
        var components = URLComponents(string: "https://auth.seismik.org/v1/oauth/login")!
        components.queryItems = [
            URLQueryItem(name: "provider", value: provider),
            URLQueryItem(name: "return_to", value: "seismik://auth/callback"),
        ]
        let flow = ASWebAuthenticationSession(
            url: components.url!, callbackURLScheme: "seismik"
        ) { [weak self] callbackURL, error in
            self?.session = nil
            if let error {
                completion(.failure(error))
                return
            }
            guard let callbackURL,
                  let code = URLComponents(url: callbackURL, resolvingAgainstBaseURL: false)?
                    .queryItems?.first(where: { $0.name == "code" })?.value,
                  !code.isEmpty else {
                completion(.failure(SeismikAPIError.malformedResponse))
                return
            }
            Task {
                do {
                    completion(.success(try await SeismikAPIClient.shared.exchangeMobileOAuthCode(code)))
                } catch {
                    completion(.failure(error))
                }
            }
        }
        flow.presentationContextProvider = self
        flow.prefersEphemeralWebBrowserSession = false
        session = flow
        if !flow.start() {
            completion(.failure(SeismikAPIError.malformedResponse))
        }
    }

    public func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let scenes = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
        return scenes.first?.windows.first(where: { $0.isKeyWindow })
            ?? ASPresentationAnchor()
    }
}

public struct FamilyLocation: Decodable, Equatable {
    public let latitude: Double
    public let longitude: Double
    public let precision: String
    public let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case latitude, longitude, precision
        case expiresAt = "expires_at"
    }
}

public struct FamilyMember: Decodable, Identifiable, Equatable {
    public let displayName: String
    public let isYou: Bool
    public let location: FamilyLocation?
    public var id: String { "\(displayName)-\(isYou)" }

    enum CodingKeys: String, CodingKey {
        case displayName = "display_name"
        case isYou = "is_you"
        case location
    }
}

public struct FamilyCircle: Decodable, Equatable {
    public let circleId: String
    public let circleName: String
    public let members: [FamilyMember]

    enum CodingKeys: String, CodingKey {
        case circleId = "circle_id"
        case circleName = "circle_name"
        case members
    }
}

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
    private static let accountSessionKey = "seismik.account_session_token"
    private static let accountProfileKey = "seismik.account_profile"

    private init() {
        let configuredURL = Bundle.main.object(forInfoDictionaryKey: "SeismikAPIBaseURL") as? String
        self.baseURL = URL(string: configuredURL ?? "") ?? URL(string: "https://api.seismik.org")!
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

    /// País del dispositivo en ISO alpha-2. El backend exige dos letras, así
    /// que una región ausente cae a CO en lugar de romper el registro.
    public static var deviceCountryCode: String {
        let region = Locale.current.regionCode ?? "ZZ"
        return region.count == 2 ? region.uppercased() : "ZZ"
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

    public var signedInAccount: SeismikAccount? {
        guard let data = UserDefaults.standard.data(forKey: Self.accountProfileKey) else { return nil }
        return try? JSONDecoder().decode(SeismikAccount.self, from: data)
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
        latitude: Double? = nil,
        longitude: Double? = nil,
        zoneId: String? = "global",
        countryCode: String = SeismikAPIClient.deviceCountryCode,
        receiveEarlyAlerts: Bool = true,
        receiveOfficialUpdates: Bool = true,
        minimumNotificationMagnitude: Double = 4.0,
        alertRadiusKm: Double = 250.0,
        criticalAlertsAuthorized: Bool = false
    ) async throws -> Bool {
        guard let pushToken = apnsToken else {
            throw SeismikAPIError.pushTokenUnavailable
        }
        let integrityToken = try await currentAppCheckToken()
        let url = baseURL.appendingPathComponent("v1/devices/register")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"

        var registrationPayload: [String: Any] = [
            "device_id": deviceId,
            "platform": "ios",
            "apns_token": pushToken,
            "country_code": countryCode.uppercased(),
            "critical_alerts_authorized": criticalAlertsAuthorized,
            "receive_early_alerts": receiveEarlyAlerts,
            "receive_official_updates": receiveOfficialUpdates,
            "minimum_notification_magnitude": minimumNotificationMagnitude,
            "alert_radius_km": alertRadiusKm,
            "locale": String(Locale.current.identifier.prefix(16)),
            "app_attest_token": integrityToken
        ]
        if let latitude, let longitude {
            registrationPayload["latitude"] = latitude
            registrationPayload["longitude"] = longitude
        } else {
            registrationPayload["zone_id"] = zoneId ?? "global"
        }

        request.httpBody = try JSONSerialization.data(withJSONObject: registrationPayload)

        let (data, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else {
            throw SeismikAPIError.malformedResponse
        }
        guard (200...299).contains(httpResponse.statusCode) else {
            let message = String(data: data, encoding: .utf8) ?? "Registro rechazado"
            throw SeismikAPIError.rejected(status: httpResponse.statusCode, message: message)
        }

        struct RegisterResponse: Decodable {
            let device_id: String
            let registered: Bool
            let crowd_token: String
            let device_session_token: String
        }

        let decoded = try JSONDecoder().decode(RegisterResponse.self, from: data)
        guard decoded.registered,
              !decoded.crowd_token.isEmpty,
              !decoded.device_session_token.isEmpty else {
            throw SeismikAPIError.malformedResponse
        }
        try keychain.set(decoded.device_session_token, for: Self.sessionTokenKey)
        try keychain.set(decoded.crowd_token, for: Self.crowdTokenKey)
        return true
    }

    // MARK: - Eventos Sísmicos

    /// Obtiene el historial de sismos recientes con soporte para autorización de sesión, reintento y caché offline.
    public func fetchRecentEvents(
        sources: [String] = ["sgc_colombia", "usgs_global"],
        days: Int = 15,
        minimumMagnitude: Double = 2.5
    ) async throws -> [SeismicEvent] {
        if !isRegistered { _ = try await registerDevice() }

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
                    let cached = loadCachedEvents()
                    if !cached.isEmpty { return cached }
                    let message = String(data: data, encoding: .utf8) ?? ""
                    throw SeismikAPIError.rejected(status: httpResponse.statusCode, message: message)
                }
            }

            return parseAndCacheEvents(data)
        } catch {
            let cached = loadCachedEvents()
            if !cached.isEmpty { return cached }
            throw error
        }
    }

    // MARK: - Estaciones Sismológicas

    /// Obtiene el listado de estaciones sismológicas activas de la red.
    public func fetchStations() async throws -> [SeismicStation] {
        if !isRegistered { _ = try await registerDevice() }
        let url = baseURL.appendingPathComponent("v1/network/stations")
        var request = URLRequest(url: url)
        if let sessionToken = deviceSessionToken {
            request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")
        }

        do {
            let (data, response) = try await session.data(for: request)
            guard let httpResponse = response as? HTTPURLResponse else {
                throw SeismikAPIError.malformedResponse
            }
            guard (200...299).contains(httpResponse.statusCode) else {
                let message = String(data: data, encoding: .utf8) ?? ""
                throw SeismikAPIError.rejected(status: httpResponse.statusCode, message: message)
            }

            struct StationsResponse: Decodable {
                let stations: [SeismicStation]
            }

            if let decoded = try? JSONDecoder().decode(StationsResponse.self, from: data) {
                return decoded.stations
            }
            throw SeismikAPIError.malformedResponse
        } catch {
            throw error
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

    // MARK: - OAuth de cuenta Seismik

    public func exchangeMobileOAuthCode(_ code: String) async throws -> SeismikAccount {
        var request = URLRequest(url: URL(string: "https://auth.seismik.org/v1/oauth/mobile/exchange")!)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONSerialization.data(withJSONObject: ["code": code])
        let (data, response) = try await session.data(for: request)
        try assertSuccess(response, data: data)
        struct Exchange: Decodable {
            let mobileSessionToken: String
            let uid: String
            let email: String
            let name: String
            enum CodingKeys: String, CodingKey {
                case mobileSessionToken = "mobile_session_token"
                case uid, email, name
            }
        }
        let result = try JSONDecoder().decode(Exchange.self, from: data)
        let account = SeismikAccount(uid: result.uid, email: result.email, name: result.name)
        try keychain.set(result.mobileSessionToken, for: Self.accountSessionKey)
        UserDefaults.standard.set(try JSONEncoder().encode(account), forKey: Self.accountProfileKey)
        return account
    }

    public func signOutAccount() throws {
        try keychain.remove(Self.accountSessionKey)
        UserDefaults.standard.removeObject(forKey: Self.accountProfileKey)
    }

    // MARK: - Círculos familiares voluntarios

    public func fetchFamilyCircle() async throws -> FamilyCircle? {
        var request = try deviceRequest(path: "v1/family/circle")
        request.httpMethod = "GET"
        let (data, response) = try await session.data(for: request)
        if (response as? HTTPURLResponse)?.statusCode == 404 { return nil }
        try assertSuccess(response, data: data)
        return try JSONDecoder().decode(FamilyCircle.self, from: data)
    }

    public func createFamilyCircle(displayName: String, circleName: String) async throws {
        _ = try await familySend(
            path: "v1/family/circle", method: "POST",
            body: ["display_name": displayName, "circle_name": circleName]
        )
    }

    public func createFamilyInvitation(displayName: String) async throws -> String {
        let data = try await familySend(
            path: "v1/family/circle/invitations", method: "POST",
            body: ["display_name": displayName]
        )
        struct Invitation: Decodable {
            let inviteCode: String
            enum CodingKeys: String, CodingKey { case inviteCode = "invite_code" }
        }
        return try JSONDecoder().decode(Invitation.self, from: data).inviteCode
    }

    public func joinFamilyCircle(inviteCode: String, displayName: String) async throws {
        _ = try await familySend(
            path: "v1/family/join", method: "POST",
            body: ["invite_code": inviteCode, "display_name": displayName]
        )
    }

    public func shareFamilyLocation(
        latitude: Double, longitude: Double, minutes: Int, precise: Bool
    ) async throws {
        _ = try await familySend(
            path: "v1/family/location", method: "PUT",
            body: [
                "latitude": latitude,
                "longitude": longitude,
                "share_minutes": minutes,
                "precision": precise ? "precise" : "approximate",
                "precise_location_consent": precise,
            ]
        )
    }

    public func stopSharingFamilyLocation() async throws {
        var request = try deviceRequest(path: "v1/family/location")
        request.httpMethod = "DELETE"
        let (data, response) = try await session.data(for: request)
        if (response as? HTTPURLResponse)?.statusCode != 204 {
            try assertSuccess(response, data: data)
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

    private func deviceRequest(path: String) throws -> URLRequest {
        guard let sessionToken = deviceSessionToken, !sessionToken.isEmpty else {
            throw SeismikAPIError.rejected(status: 401, message: "El dispositivo aún se está preparando")
        }
        var request = URLRequest(url: baseURL.appendingPathComponent(path))
        request.setValue(sessionToken, forHTTPHeaderField: "X-Seismik-Device-Session")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        return request
    }

    @discardableResult
    private func familySend(path: String, method: String, body: [String: Any]) async throws -> Data {
        var request = try deviceRequest(path: path)
        request.httpMethod = method
        request.httpBody = try JSONSerialization.data(withJSONObject: body)
        let (data, response) = try await session.data(for: request)
        try assertSuccess(response, data: data)
        return data
    }

    private func assertSuccess(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw SeismikAPIError.rejected(
                status: (response as? HTTPURLResponse)?.statusCode ?? 0,
                message: String(data: data, encoding: .utf8) ?? "El servidor rechazó la solicitud"
            )
        }
    }

    /// Obtiene un token efímero emitido por Firebase App Check y respaldado
    /// por DeviceCheck. Nunca se persiste ni se sustituye por texto de prueba.
    private func currentAppCheckToken() async throws -> String {
        try await withCheckedThrowingContinuation { continuation in
            AppCheck.appCheck().token(forcingRefresh: false) { token, error in
                if let error {
                    continuation.resume(throwing: error)
                    return
                }
                guard let value = token?.token, !value.isEmpty else {
                    continuation.resume(throwing: SeismikAPIError.malformedResponse)
                    return
                }
                continuation.resume(returning: value)
            }
        }
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

