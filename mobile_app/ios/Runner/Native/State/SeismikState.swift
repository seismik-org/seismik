import Foundation
import SwiftUI
import Combine

/// Estado global reactivo para la aplicación Seismik en iOS.
@MainActor
public final class SeismikState: ObservableObject {
    public static let shared = SeismikState()

    @Published public var events: [SeismicEvent] = SeismicEvent.sampleEvents
    @Published public var stations: [SeismicStation] = []
    @Published public var selectedEvent: SeismicEvent?
    @Published public var activeAlert: SeismicEvent?
    @Published public var isRefreshing: Bool = false
    @Published public var isOnline: Bool = true
    @Published public var lastUpdated: Date?
    @Published public var isRegistered: Bool = false
    @Published public var pendingReportCount: Int = 0

    // Preferencias de filtrado y monitoreo
    @AppStorage("seismik.history_days") public var historyDays: Int = 7
    @AppStorage("seismik.min_magnitude") public var minMagnitude: Double = 2.5
    @AppStorage("seismik.alert_radius_km") public var alertRadiusKm: Double = 250.0
    @AppStorage("seismik.min_notification_magnitude") public var minimumNotificationMagnitude: Double = 4.0
    @AppStorage("seismik.include_preliminary") public var includePreliminaryEvents: Bool = true
    @AppStorage("seismik.receive_early_alerts") public var receiveEarlyAlerts: Bool = true
    @AppStorage("seismik.receive_official_updates") public var receiveOfficialUpdates: Bool = true

    private let apiClient = SeismikAPIClient.shared
    private let locationManager = LocationManager.shared

    public init() {
        self.isRegistered = apiClient.isRegistered
        Task {
            locationManager.requestPermission()
            locationManager.startUpdating()
            await updateRegistration()
            await refreshData()
        }
    }

    /// Sincroniza el registro de este dispositivo y las preferencias con el servidor.
    public func updateRegistration() async {
        let lat = locationManager.userCoordinate?.latitude ?? 4.65
        let lon = locationManager.userCoordinate?.longitude ?? -74.05
        do {
            let registered = try await apiClient.registerDevice(
                latitude: lat,
                longitude: lon,
                countryCode: "CO",
                receiveEarlyAlerts: receiveEarlyAlerts,
                receiveOfficialUpdates: receiveOfficialUpdates,
                minimumNotificationMagnitude: minimumNotificationMagnitude,
                alertRadiusKm: alertRadiusKm
            )
            self.isRegistered = registered
        } catch {
            self.isRegistered = apiClient.isRegistered
        }
    }

    /// Actualiza el catálogo de sismos y estaciones desde la red.
    public func refreshData() async {
        isRefreshing = true
        HapticManager.light()

        do {
            async let fetchedEvents = apiClient.fetchRecentEvents(
                days: historyDays,
                minimumMagnitude: minMagnitude
            )
            async let fetchedStations = apiClient.fetchStations()

            let (newEvents, newStations) = try await (fetchedEvents, fetchedStations)
            let filtered = includePreliminaryEvents ? newEvents : newEvents.filter { !$0.isPreliminary }
            if !filtered.isEmpty {
                self.events = filtered.sorted { ($0.detectedAt ?? Date.distantPast) > ($1.detectedAt ?? Date.distantPast) }
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
        withAnimation(.easeOut(duration: 0.25)) {
            self.activeAlert = nil
        }
        HapticManager.light()
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
        withAnimation(.spring(response: 0.45, dampingFraction: 0.75)) {
            self.activeAlert = testEvent
        }
        HapticManager.heavy()
    }
}
