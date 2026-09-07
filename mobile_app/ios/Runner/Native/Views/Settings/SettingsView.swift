import CoreLocation
import SwiftUI
import UIKit
import UserNotifications

/// Ajustes de iPhone basados en controles y jerarquía nativos de iOS.
public struct SettingsView: View {
    @ObservedObject var state: SeismikState
    public let showsCloseButton: Bool
    @ObservedObject private var locationManager = LocationManager.shared
    @Environment(\.dismiss) private var dismiss

    @State private var notificationStatus: UNAuthorizationStatus = .notDetermined
    @State private var browserDestination: BrowserDestination?

    public init(state: SeismikState, showsCloseButton: Bool = true) {
        self.state = state
        self.showsCloseButton = showsCloseButton
    }

    public var body: some View {
        CompatibleNavigationStack {
            Form {
                Section {
                    Toggle("Alertas tempranas", isOn: $state.receiveEarlyAlerts)
                        .onChange(of: state.receiveEarlyAlerts) { _ in saveAlertPreferences() }
                    Toggle("Actualizaciones oficiales", isOn: $state.receiveOfficialUpdates)
                        .onChange(of: state.receiveOfficialUpdates) { _ in saveAlertPreferences() }

                    Stepper(value: $state.minimumNotificationMagnitude, in: 2...8, step: 0.5) {
                        ValueRow(
                            title: "Magnitud mínima",
                            value: "M \(String(format: "%.1f", state.minimumNotificationMagnitude))"
                        )
                    }
                    .onChange(of: state.minimumNotificationMagnitude) { _ in saveAlertPreferences() }

                    Stepper(value: $state.alertRadiusKm, in: 50...2_000, step: 50) {
                        ValueRow(title: "Distancia máxima", value: "\(Int(state.alertRadiusKm)) km")
                    }
                    .onChange(of: state.alertRadiusKm) { _ in saveAlertPreferences() }

                    Button("Probar una alerta") { runAlertTest() }
                } header: {
                    Text("Alertas")
                } footer: {
                    Text("Los filtros se guardan en Seismik y se aplican antes de enviar una notificación.")
                }

                Section("Historial y mapa") {
                    Stepper(value: $state.minMagnitude, in: 0...8, step: 0.5) {
                        ValueRow(
                            title: "Magnitud visible",
                            value: "M \(String(format: "%.1f", state.minMagnitude))"
                        )
                    }
                    .onChange(of: state.minMagnitude) { _ in refreshHistory() }

                    Picker("Periodo", selection: $state.historyDays) {
                        Text("24 horas").tag(1)
                        Text("7 días").tag(7)
                        Text("15 días").tag(15)
                        Text("30 días").tag(30)
                    }
                    .onChange(of: state.historyDays) { _ in refreshHistory() }

                    Toggle("Detecciones preliminares", isOn: $state.includePreliminaryEvents)
                        .onChange(of: state.includePreliminaryEvents) { _ in refreshHistory() }

                    Picker("Mapa del historial", selection: $state.appMapType) {
                        Text("Estándar").tag("standard")
                        Text("Satélite").tag("satellite")
                        Text("Híbrido").tag("hybrid")
                    }

                    Picker("Abrir epicentro con", selection: $state.mapProvider) {
                        Text("Apple Maps").tag("apple")
                        Text("Google Maps").tag("google")
                    }
                }

                Section {
                    Toggle("Detección colaborativa", isOn: $state.crowdsourcingEnabled)
                        .onChange(of: state.crowdsourcingEnabled) { _ in state.syncCrowdsourcing() }
                    Toggle("Ubicación precisa en reportes", isOn: $state.preciseLocationByDefault)
                } header: {
                    Text("Privacidad y sensores")
                } footer: {
                    Text("Los reportes necesitan una ubicación. La detección colaborativa usa el acelerómetro únicamente cuando está activada.")
                }

                Section("Permisos de este iPhone") {
                    Button(action: openSystemSettings) {
                        StatusRow(title: "Notificaciones", value: notificationStatusLabel, symbol: "bell.fill")
                    }
                    .foregroundStyle(.primary)

                    Button {
                        if locationManager.authorizationStatus == .notDetermined {
                            locationManager.requestPermission()
                        } else {
                            openSystemSettings()
                        }
                    } label: {
                        StatusRow(title: "Ubicación", value: locationStatusLabel, symbol: "location.fill")
                    }
                    .foregroundStyle(.primary)
                }

                Section("Estado") {
                    StatusRow(
                        title: "Dispositivo",
                        value: state.isRegistered ? "Registrado" : "Pendiente",
                        symbol: state.isRegistered ? "checkmark.shield.fill" : "shield.fill"
                    )
                    if state.pendingReportCount > 0 {
                        ValueRow(title: "Reportes por enviar", value: "\(state.pendingReportCount)")
                        Button("Reintentar sincronización") {
                            Task { await state.flushPendingReports() }
                        }
                    }
                    if let issue = state.registrationIssue, !state.isRegistered {
                        Text(issue)
                            .font(.footnote)
                            .foregroundStyle(.secondary)
                    }
                }

                Section("Acerca de Seismik") {
                    ValueRow(title: "Versión", value: versionDescription)
                    Button("Privacidad") {
                        browserDestination = BrowserDestination(url: URL(string: "https://seismik.org/terms-of-privacy")!)
                    }
                    Button("Términos del servicio") {
                        browserDestination = BrowserDestination(url: URL(string: "https://seismik.org/terms-of-service")!)
                    }
                }
            }
            .navigationTitle("Configuración")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    if showsCloseButton {
                        Button("Listo") { dismiss() }
                    }
                }
            }
            .task {
                notificationStatus = await UNUserNotificationCenter.current()
                    .notificationSettings().authorizationStatus
            }
            .sheet(item: $browserDestination) { destination in
                InAppBrowserView(url: destination.url)
                    .ignoresSafeArea()
            }
        }
    }

    private var versionDescription: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
        return "\(version) (\(build))"
    }

    private var notificationStatusLabel: String {
        switch notificationStatus {
        case .authorized: return "Permitidas"
        case .provisional: return "Provisionales"
        case .ephemeral: return "Temporales"
        case .denied: return "Desactivadas"
        case .notDetermined: return "Sin solicitar"
        @unknown default: return "Desconocido"
        }
    }

    private var locationStatusLabel: String {
        switch locationManager.authorizationStatus {
        case .authorizedAlways: return "Siempre"
        case .authorizedWhenInUse: return "Al usar la app"
        case .denied, .restricted: return "Desactivada"
        case .notDetermined: return "Sin solicitar"
        @unknown default: return "Desconocida"
        }
    }

    private func saveAlertPreferences() {
        Task { await state.applyAlertPreferences() }
    }

    private func refreshHistory() {
        Task { await state.refreshData() }
    }

    private func runAlertTest() {
        if showsCloseButton {
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) { state.runAlertSimulation() }
        } else {
            state.runAlertSimulation()
        }
    }

    private func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        UIApplication.shared.open(url)
    }
}

private struct ValueRow: View {
    let title: String
    let value: String

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            Text(value).foregroundStyle(.secondary).monospacedDigit()
        }
    }
}

private struct StatusRow: View {
    let title: String
    let value: String
    let symbol: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).frame(width: 24)
            Text(title)
            Spacer()
            Text(value).foregroundStyle(.secondary)
        }
    }
}
