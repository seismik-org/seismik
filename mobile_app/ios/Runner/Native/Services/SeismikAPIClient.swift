import Foundation

/// Cliente de red nativo en Swift con async/await para la API de Seismik.
public final class SeismikAPIClient {
    public static let shared = SeismikAPIClient()

    private let baseURL: URL
    private let session: URLSession

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

    /// Identificador único del dispositivo (UUID persistido en UserDefaults).
    public var deviceId: String {
        let key = "seismik.device_id"
        if let existing = UserDefaults.standard.string(forKey: key) {
            return existing
        }
        let newId = UUID().uuidString
        UserDefaults.standard.set(newId, forKey: key)
        return newId
    }

    // MARK: - Eventos Sísmicos

    /// Obtiene el historial de sismos recientes oficiales y preliminares.
    public func fetchRecentEvents(
        sources: [String] = ["sgc_colombia", "usgs_global"],
        days: Int = 15,
        minimumMagnitude: Double = 2.5
    ) async throws -> [SeismicEvent] {
        var components = URLComponents(url: baseURL.appendingPathComponent("v1/events/history"), resolvingAgainstBaseURL: true)
        components?.queryItems = [
            URLQueryItem(name: "sources", value: sources.sorted().joined(separator: ",")),
            URLQueryItem(name: "days", value: "\(days)"),
            URLQueryItem(name: "minimum_magnitude", value: String(format: "%.1f", minimumMagnitude)),
            URLQueryItem(name: "limit", value: "200")
        ]

        guard let url = components?.url else {
            throw URLError(.badURL)
        }

        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }

        // Estructura envolvente del backend {"events": [...]}
        struct EventsResponse: Decodable {
            let events: [SeismicEvent]
        }

        if let decoded = try? JSONDecoder().decode(EventsResponse.self, from: data) {
            return decoded.events
        } else if let rawEvents = try? JSONDecoder().decode([SeismicEvent].self, from: data) {
            return rawEvents
        }

        return []
    }

    // MARK: - Estaciones Sismológicas

    /// Obtiene el listado de estaciones sismológicas activas de la red.
    public func fetchStations() async throws -> [SeismicStation] {
        let url = baseURL.appendingPathComponent("v1/network/stations")
        let (data, response) = try await session.data(from: url)
        guard let httpResponse = response as? HTTPURLResponse, (200...299).contains(httpResponse.statusCode) else {
            throw URLError(.badServerResponse)
        }

        struct StationsResponse: Decodable {
            let stations: [SeismicStation]
        }

        let decoded = try JSONDecoder().decode(StationsResponse.self, from: data)
        return decoded.stations
    }

    // MARK: - Reportes Ciudadanos

    /// Envía un reporte de sismo sentido (DYFI).
    public func submitFeltReport(_ report: FeltReportPayload) async throws -> Bool {
        let url = baseURL.appendingPathComponent("v1/reports/felt")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpBody = try JSONEncoder().encode(report)

        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { return false }
        return (200...299).contains(httpResponse.statusCode)
    }

    /// Envía un reporte de daños estructurales.
    public func submitDamageReport(_ report: DamageReportPayload) async throws -> Bool {
        let url = baseURL.appendingPathComponent("v1/reports/damage")
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.httpBody = try JSONEncoder().encode(report)

        let (_, response) = try await session.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse else { return false }
        return (200...299).contains(httpResponse.statusCode)
    }
}
