import Combine
import Foundation
import SwiftUI
import UserNotifications

/// Estado global reactivo para la aplicación Seismik en iOS.
@MainActor
public final class SeismikState: ObservableObject {
    public static let shared = SeismikState()

    /// Arranca vacío a propósito: mostrar sismos de ejemplo con el sello de
    /// una agencia oficial sería peor que no mostrar nada.
    @Published public var events: [SeismicEvent] = []
    @Published public var stations: [SeismicStation] = []
    @Published public var selectedEvent: SeismicEvent?
    @Published public var activeAlert: SeismicEvent?
    @Published public var isRefreshing: Bool = false
    @Published public var isOnline: Bool = true
    @Published public var lastUpdated: Date?
    @Published public var isRegistered: Bool = false
    @Published public var pendingReportCount: Int = 0
    /// Mensaje de sincronización para la interfaz (reportes o alertas).
    @Published public var syncMessage: String?
    /// Motivo por el que el alta no pudo completarse, si aplica.
    @Published public var registrationIssue: String?

    // Preferencias de filtrado y monitoreo
    @AppStorage("seismik.history_days") public var historyDays: Int = 7
    @AppStorage("seismik.min_magnitude") public var minMagnitude: Double = 2.5
    @AppStorage("seismik.alert_radius_km") public var alertRadiusKm: Double = 250.0
    @AppStorage("seismik.min_notification_magnitude") public var minimumNotificationMagnitude: Double = 4.0
    @AppStorage("seismik.include_preliminary") public var includePreliminaryEvents: Bool = true
    @AppStorage("seismik.receive_early_alerts") public var receiveEarlyAlerts: Bool = true
    @AppStorage("seismik.receive_official_updates") public var receiveOfficialUpdates: Bool = true
    @AppStorage("seismik.map_provider") public var mapProvider: String = "system"
    @AppStorage("seismik.app_map_type") public var appMapType: String = "standard"
    @AppStorage("seismik.crowdsourcing_enabled") public var crowdsourcingEnabled: Bool = true
    @AppStorage("seismik.precise_location") public var preciseLocationByDefault: Bool = false
    @AppStorage("seismik.history_sources") public var historySourcesRaw: String = "sgc_colombia,usgs_global,seismik_seedlink_preliminary"

    private let apiClient = SeismikAPIClient.shared
    private let locationManager = LocationManager.shared
    private let motion = MotionDetector.shared
    private var locationRegistration: AnyCancellable?
    /// App Check no admite dos obtenciones simultáneas durante el arranque.
    /// Centralizar el alta evita `ParallelWaitError` y registros intermitentes.
    private var registrationInProgress = false

    public init() {
        self.isRegistered = apiClient.isRegistered
        self.pendingReportCount = apiClient.pendingReportCount
        locationRegistration = locationManager.$userCoordinate
            .compactMap { $0 }
            .first()
            .sink { [weak self] _ in
                Task { @MainActor in
                    await self?.updateRegistration()
                    await self?.refreshData()
                }
            }
        Task {
            locationManager.requestPermission()
            locationManager.startUpdating()
            await updateRegistration()
            await refreshData()
            await flushPendingReports()
            await syncMissedAlerts()
            syncCrowdsourcing()
        }
    }

    /// Sincroniza el registro de este dispositivo y las preferencias con el servidor.
    ///
    /// El umbral de magnitud y el radio viven en el servidor: sin volver a
    /// registrar el dispositivo, un cambio de preferencia no llegaría al
    /// despachador y la persona seguiría recibiendo lo mismo que antes.
    public func updateRegistration() async {
        guard !registrationInProgress else { return }
        registrationInProgress = true
        defer { registrationInProgress = false }
        let coordinate = locationManager.userCoordinate
        // El despachador decide con este dato si el aviso puede sonar como
        // alerta crítica; enviarlo fijo en falso lo desactivaba siempre.
        let settings = await UNUserNotificationCenter.current().notificationSettings()
        let criticalAllowed = settings.criticalAlertSetting == .enabled
        do {
            let registered = try await apiClient.registerDevice(
                latitude: coordinate?.latitude,
                longitude: coordinate?.longitude,
                zoneId: coordinate == nil ? "global" : nil,
                receiveEarlyAlerts: receiveEarlyAlerts,
                receiveOfficialUpdates: receiveOfficialUpdates,
                minimumNotificationMagnitude: minimumNotificationMagnitude,
                alertRadiusKm: alertRadiusKm,
                criticalAlertsAuthorized: criticalAllowed
            )
            self.isRegistered = registered
            self.registrationIssue = registered ? nil : "El servidor no aceptó el registro."
        } catch let error as SeismikAPIError {
            self.isRegistered = apiClient.isRegistered
            // Al arrancar es normal: APNs entrega el token unos instantes
            // después y AppDelegate vuelve a llamar aquí.
            self.registrationIssue = error.errorDescription
        } catch {
            self.isRegistered = apiClient.isRegistered
            self.registrationIssue = error.localizedDescription
        }
    }

    /// Reenvía los reportes guardados sin conexión.
    public func flushPendingReports() async {
        let result = await apiClient.flushPendingReports()
        pendingReportCount = result.remaining
        if result.sent > 0 {
            syncMessage = result.sent == 1
                ? "Se envió 1 reporte guardado sin conexión."
                : "Se enviaron \(result.sent) reportes guardados sin conexión."
        } else if result.remaining > 0 {
            syncMessage = result.remaining == 1
                ? "1 reporte espera conexión para enviarse."
                : "\(result.remaining) reportes esperan conexión para enviarse."
        } else if result.changed {
            syncMessage = nil
        }
    }

    /// Recupera las alertas emitidas mientras el teléfono estuvo sin conexión.
    public func syncMissedAlerts() async {
        let missed = await apiClient.fetchMissedAlerts()
        guard !missed.isEmpty else { return }
        let known = Set(events.map(\.id))
        let added = missed.filter { !known.contains($0.id) }
        guard !added.isEmpty else { return }
        events = (added + events)
            .sorted { ($0.detectedAt ?? .distantPast) > ($1.detectedAt ?? .distantPast) }
        syncMessage = added.count == 1
            ? "Se recuperó 1 alerta recibida sin conexión."
            : "Se recuperaron \(added.count) alertas recibidas sin conexión."
    }

    /// Arranca o detiene la detección colaborativa según la preferencia.
    public func syncCrowdsourcing() {
        guard crowdsourcingEnabled, isRegistered else {
            motion.stop()
            return
        }
        motion.start()
    }

    /// Aplica un cambio de preferencias de alerta: lo persiste en el servidor.
    public func applyAlertPreferences() async {
        await updateRegistration()
        syncCrowdsourcing()
    }

    /// Actualiza el catálogo de sismos y estaciones desde la red.
    public func refreshData() async {
        isRefreshing = true
        HapticManager.light()

        if !apiClient.isRegistered {
            await updateRegistration()
            guard apiClient.isRegistered else {
                isOnline = false
                isRefreshing = false
                return
            }
        }

        do {
            async let fetchedEvents = apiClient.fetchRecentEvents(
                sources: historySourceIds,
                days: historyDays,
                minimumMagnitude: minMagnitude
            )
            async let fetchedStations = apiClient.fetchStations()

            let (newEvents, newStations) = try await (fetchedEvents, fetchedStations)
            let filtered = includePreliminaryEvents ? newEvents : newEvents.filter { !$0.isPreliminary }
            // Se asigna aunque venga vacío: si el filtro actual no deja ningún
            // sismo, la lista debe quedar vacía en vez de conservar la anterior.
            self.events = filtered.sorted {
                ($0.detectedAt ?? Date.distantPast) > ($1.detectedAt ?? Date.distantPast)
            }
            if !newStations.isEmpty {
                self.stations = newStations
            }
            self.isOnline = true
            self.isRegistered = apiClient.isRegistered
            self.lastUpdated = Date()
            HapticManager.selection()
        } catch {
            self.isOnline = false
        }

        isRefreshing = false
        await flushPendingReports()
        await syncMissedAlerts()
    }

    /// Selecciona un sismo para desplegar su vista de detalle.
    public func selectEvent(_ event: SeismicEvent?) {
        withAnimation(.spring(response: 0.38, dampingFraction: 0.82)) {
            self.selectedEvent = event
        }
        if event != nil {
            HapticManager.light()
        }
    }

    /// Descarta la alerta sísmica en pantalla.
    public func dismissAlert() {
        AlertSoundPlayer.shared.stop()
        withAnimation(.easeOut(duration: 0.25)) {
            self.activeAlert = nil
        }
        HapticManager.light()
    }

    /// Convierte el contenido APNs en estado visible. Las alertas tempranas se
    /// muestran de inmediato; una actualización oficial se abre como detalle.
    public func handleRemoteNotification(_ userInfo: [AnyHashable: Any]) {
        guard let event = SeismicEvent(notificationUserInfo: userInfo) else {
            Task { await refreshData() }
            return
        }
        if !events.contains(where: { $0.id == event.id }) {
            events.insert(event, at: 0)
        }
        if event.isPreliminary || (event.magnitude ?? 0) >= 4.0 {
            activeAlert = event
            HapticManager.heavy()
        } else {
            selectedEvent = event
        }
    }

    /// Dispara una simulación de alerta de emergencia para pruebas del usuario.
    public func runAlertSimulation() {
        let testEvent = SeismicEvent(
            id: "test-sim-\(Int(Date().timeIntervalSince1970))",
            place: "Epicentro simulado · Pruebas de Alerta",
            magnitude: 6.4,
            depthKm: 18.0,
            latitude: locationManager.userCoordinate?.latitude ?? 4.65,
            longitude: locationManager.userCoordinate?.longitude ?? -74.05,
            detectedAt: Date(),
            sourceId: "seismik_test",
            agency: "Simulacro Seismik",
            isPreliminary: false,
            intensityMmi: 7,
            tsunamiWarning: false
        )
        if !events.contains(where: { $0.id == testEvent.id }) {
            events.insert(testEvent, at: 0)
        }
        withAnimation(.spring(response: 0.45, dampingFraction: 0.75)) {
            self.activeAlert = testEvent
        }
        HapticManager.heavy()
    }

    /// Identificador único persistente de este dispositivo.
    public var deviceId: String {
        apiClient.deviceId
    }

    /// Verifica si una fuente geológica está activa en los filtros.
    public func isSourceActive(_ sourceKey: String) -> Bool {
        let items = historySourcesRaw.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
        return items.contains(sourceKey)
    }

    /// Alterna la inclusión de una fuente geológica en el historial.
    public func toggleSource(_ sourceKey: String) {
        var items = historySourcesRaw.split(separator: ",").map { String($0.trimmingCharacters(in: .whitespaces)) }
        if let idx = items.firstIndex(of: sourceKey) {
            items.remove(at: idx)
        } else {
            items.append(sourceKey)
        }
        historySourcesRaw = items.joined(separator: ",")
        HapticManager.selection()
        Task { await refreshData() }
    }

    private var historySourceIds: [String] {
        var items = historySourcesRaw
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
        if includePreliminaryEvents {
            if !items.contains("seismik_seedlink_preliminary") {
                items.append("seismik_seedlink_preliminary")
            }
        } else {
            items.removeAll { $0 == "seismik_seedlink_preliminary" }
        }
        if items.isEmpty { return ["sgc_colombia", "usgs_global"] }
        return Array(Set(items)).sorted()
    }

    /// Alterna cíclicamente el estilo del mapa nativo entre Estándar, Satélite e Híbrido.
    public func cycleMapType() {
        switch appMapType {
        case "standard": appMapType = "satellite"
        case "satellite": appMapType = "hybrid"
        default: appMapType = "standard"
        }
        HapticManager.selection()
    }
}

