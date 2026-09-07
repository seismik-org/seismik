import Foundation

/// Tipo de reporte ciudadano en espera de sincronización.
public enum PendingReportKind: String, Codable {
    case felt
    case damage

    public var path: String {
        switch self {
        case .felt: return "v1/reports/felt"
        case .damage: return "v1/reports/damage"
        }
    }

    public var label: String {
        switch self {
        case .felt: return "Sismo sentido"
        case .damage: return "Reporte de daños"
        }
    }
}

/// Reporte guardado en el dispositivo mientras no hay red.
///
/// Se conserva el **cuerpo ya codificado**, no el modelo: la firma HMAC cubre
/// esos bytes exactos, así que volver a codificar el objeto al reintentar podría
/// producir un orden de claves distinto y una firma que el servidor rechaza.
/// Por lo mismo, `report_id` y `observed_at` no cambian entre intentos: el
/// servidor reconoce el reenvío como el mismo reporte y la hora registrada
/// sigue siendo la del sismo, no la de la sincronización.
public struct PendingReport: Codable, Identifiable, Equatable {
    public var id: String { reportId }
    public let reportId: String
    public let kind: PendingReportKind
    public let body: Data
    public let queuedAt: Date
    public var attempts: Int
    public var lastError: String?

    public init(
        reportId: String,
        kind: PendingReportKind,
        body: Data,
        queuedAt: Date = Date(),
        attempts: Int = 0,
        lastError: String? = nil
    ) {
        self.reportId = reportId
        self.kind = kind
        self.body = body
        self.queuedAt = queuedAt
        self.attempts = attempts
        self.lastError = lastError
    }
}

/// Resultado de un intento de sincronización de la cola.
public struct QueueFlushResult: Equatable {
    public let sent: Int
    public let remaining: Int
    public let discarded: Int
    public let lastError: String?

    public var changed: Bool { sent > 0 || discarded > 0 }
}

/// El servidor rechazó el reporte de forma definitiva; reintentarlo repetiría
/// el mismo error.
public struct PermanentReportRejection: Error {
    public let message: String
    public init(_ message: String) { self.message = message }
}

/// Cola persistente de reportes ciudadanos creados sin conexión.
///
/// Un sismo suele dejar a la gente sin datos justo cuando más importa reportar.
/// Refleja la política de la app de Android para que ambas plataformas se
/// comporten igual: hasta 50 reportes, 12 intentos y 30 días de vigencia.
public final class OfflineReportQueue {
    public static let shared = OfflineReportQueue()

    private let storageKey = "seismik.pending_reports"
    private let defaults: UserDefaults
    private let maxEntries: Int
    private let maxAttempts: Int
    private let maxAge: TimeInterval
    private let lock = NSLock()

    public init(
        defaults: UserDefaults = .standard,
        maxEntries: Int = 50,
        maxAttempts: Int = 12,
        maxAge: TimeInterval = 30 * 24 * 60 * 60
    ) {
        self.defaults = defaults
        self.maxEntries = maxEntries
        self.maxAttempts = maxAttempts
        self.maxAge = maxAge
    }

    // MARK: - Lectura y escritura

    public func load() -> [PendingReport] {
        lock.lock()
        defer { lock.unlock() }
        return loadUnlocked()
    }

    public var pendingCount: Int { load().count }

    /// Guarda un reporte al final de la cola, sustituyendo el mismo `report_id`.
    public func enqueue(_ report: PendingReport) {
        lock.lock()
        defer { lock.unlock() }
        var queue = loadUnlocked().filter { $0.reportId != report.reportId }
        queue.append(report)
        // Ante saturación se conservan los más recientes: son los que todavía
        // describen la emergencia en curso.
        if queue.count > maxEntries {
            queue = Array(queue.suffix(maxEntries))
        }
        writeUnlocked(queue)
    }

    public func remove(reportId: String) {
        lock.lock()
        defer { lock.unlock() }
        writeUnlocked(loadUnlocked().filter { $0.reportId != reportId })
    }

    public func clear() {
        lock.lock()
        defer { lock.unlock() }
        defaults.removeObject(forKey: storageKey)
    }

    // MARK: - Sincronización

    /// Reenvía la cola en orden. Se detiene ante el primer fallo transitorio
    /// para no gastar batería ni datos repitiendo el mismo error de red.
    @discardableResult
    public func flush(
        now: Date = Date(),
        send: (PendingReport) async throws -> Void
    ) async -> QueueFlushResult {
        let queue = load()
        if queue.isEmpty {
            return QueueFlushResult(sent: 0, remaining: 0, discarded: 0, lastError: nil)
        }

        var remaining: [PendingReport] = []
        var sent = 0
        var discarded = 0
        var lastError: String?
        var offline = false

        for report in queue {
            if offline {
                remaining.append(report)
                continue
            }
            if now.timeIntervalSince(report.queuedAt) > maxAge {
                discarded += 1
                continue
            }
            do {
                try await send(report)
                sent += 1
            } catch let rejection as PermanentReportRejection {
                discarded += 1
                lastError = rejection.message
            } catch {
                lastError = error.localizedDescription
                var retried = report
                retried.attempts += 1
                retried.lastError = lastError
                if retried.attempts >= maxAttempts {
                    discarded += 1
                } else {
                    remaining.append(retried)
                    offline = true
                }
            }
        }

        lock.lock()
        writeUnlocked(remaining)
        lock.unlock()

        return QueueFlushResult(
            sent: sent,
            remaining: remaining.count,
            discarded: discarded,
            lastError: lastError
        )
    }

    // MARK: - Privados

    private func loadUnlocked() -> [PendingReport] {
        guard let raw = defaults.data(forKey: storageKey) else { return [] }
        // Una entrada corrupta no debe bloquear las demás.
        guard let decoded = try? JSONDecoder().decode([PendingReport].self, from: raw) else {
            defaults.removeObject(forKey: storageKey)
            return []
        }
        return decoded
    }

    private func writeUnlocked(_ queue: [PendingReport]) {
        if queue.isEmpty {
            defaults.removeObject(forKey: storageKey)
            return
        }
        guard let encoded = try? JSONEncoder().encode(queue) else { return }
        defaults.set(encoded, forKey: storageKey)
    }
}
