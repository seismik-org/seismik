import CoreLocation
import SwiftUI
import UIKit
import UserNotifications

/// Preferencias nativas de iPhone. Los permisos del sistema se consultan, no se imitan.
public struct SettingsView: View {
    @ObservedObject var state: SeismikState
    public let showsCloseButton: Bool
    @ObservedObject private var locationManager = LocationManager.shared
    @Environment(\.dismiss) private var dismiss

    @AppStorage("seismik.map_provider") private var mapProvider = "apple"
    @State private var notificationStatus: UNAuthorizationStatus = .notDetermined

    public init(state: SeismikState, showsCloseButton: Bool = true) {
        self.state = state
        self.showsCloseButton = showsCloseButton
    }

    public var body: some View {
        CompatibleNavigationStack {
            Form {
                Section {
                    Toggle("Alertas tempranas", isOn: $state.receiveEarlyAlerts)
                        .tint(SeismikColors.systemBlue)
                        .onChange(of: state.receiveEarlyAlerts) { _ in synchronizePreferences() }

                    Toggle("Actualizaciones oficiales", isOn: $state.receiveOfficialUpdates)
                        .tint(SeismikColors.systemBlue)
                        .onChange(of: state.receiveOfficialUpdates) { _ in synchronizePreferences() }

                    Stepper(value: $state.minimumNotificationMagnitude, in: 2.0...8.0, step: 0.5) {
                        SettingsValueRow(
                            title: "Magnitud mínima",
                            value: "M \(String(format: "%.1f", state.minimumNotificationMagnitude))"
                        )
                    }
                    .onChange(of: state.minimumNotificationMagnitude) { _ in synchronizePreferences() }

                    Stepper(value: $state.alertRadiusKm, in: 10...2_000, step: 50) {
                        SettingsValueRow(title: "Radio de alerta", value: "\(Int(state.alertRadiusKm)) km")
                    }
                    .onChange(of: state.alertRadiusKm) { _ in synchronizePreferences() }
                } header: {
                    Text("Alertas sísmicas")
                } footer: {
                    Text("Seismik filtra en el servidor los avisos por magnitud y distancia. Ninguna alerta puede garantizar tiempo previo al movimiento.")
                }

                Section("Historial y mapa") {
                    Stepper(value: $state.minMagnitude, in: 0...8, step: 0.5) {
                        SettingsValueRow(
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

                    Toggle("Incluir detecciones preliminares", isOn: $state.includePreliminaryEvents)
                        .onChange(of: state.includePreliminaryEvents) { _ in refreshHistory() }

                    Picker("Abrir epicentro con", selection: $mapProvider) {
                        Label("Apple Maps", systemImage: "apple.logo").tag("apple")
                        Label("Google Maps", systemImage: "map").tag("google")
                    }
                }

                Section("Permisos de este iPhone") {
                    Button(action: openSystemSettings) {
                        SettingsStatusRow(
                            title: "Notificaciones",
                            value: notificationStatusLabel,
                            symbol: "bell.badge",
                            color: notificationAllowed ? SeismikColors.emerald : SeismikColors.amber
                        )
                    }
                    .foregroundColor(.primary)

                    Button {
                        if locationManager.authorizationStatus == .notDetermined {
                            locationManager.requestPermission()
                        } else {
                            openSystemSettings()
                        }
                    } label: {
                        SettingsStatusRow(
                            title: "Ubicación",
                            value: locationStatusLabel,
                            symbol: "location.fill",
                            color: locationAuthorized ? SeismikColors.emerald : SeismikColors.amber
                        )
                    }
                    .foregroundColor(.primary)
                } footer: {
                    Text("iOS controla estos permisos. Toca una fila para revisarlos en Ajustes.")
                }

                Section("Estado de Seismik") {
                    SettingsStatusRow(
                        title: "Dispositivo",
                        value: state.isRegistered ? "Registrado" : "Pendiente",
                        symbol: state.isRegistered ? "checkmark.shield.fill" : "exclamationmark.shield",
                        color: state.isRegistered ? SeismikColors.emerald : SeismikColors.amber
                    )

                    if state.pendingReportCount > 0 {
                        SettingsValueRow(title: "Reportes por sincronizar", value: "\(state.pendingReportCount)")
                    }

                    Button(action: runAlertTest) {
                        Label("Probar alerta en este iPhone", systemImage: "bell.and.waves.left.and.right.fill")
                    }
                }

                Section("Acerca de Seismik") {
                    SettingsValueRow(title: "Versión", value: versionDescription)
                    SettingsValueRow(title: "Mapa", value: "Apple MapKit")
                    Link("Privacidad", destination: URL(string: "https://seismik.org/terms-of-privacy")!)
                    Link("Términos del servicio", destination: URL(string: "https://seismik.org/terms-of-service")!)
                }
            }
            .navigationTitle("Configuración")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                if showsCloseButton {
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Listo") { dismiss() }
                    }
                }
            }
            .task {
                notificationStatus = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
            }
        }
    }

    private var versionDescription: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "—"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "—"
        return "\(version) (\(build))"
    }

    private var notificationAllowed: Bool {
        notificationStatus == .authorized || notificationStatus == .provisional
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

    private var locationAuthorized: Bool {
        locationManager.authorizationStatus == .authorizedAlways
            || locationManager.authorizationStatus == .authorizedWhenInUse
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

    private func synchronizePreferences() {
        Task { await state.updateRegistration() }
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

private struct SettingsValueRow: View {
    let title: String
    let value: String

    var body: some View {
        HStack {
            Text(title)
            Spacer()
            Text(value)
                .foregroundColor(.secondary)
                .monospacedDigit()
        }
    }
}

private struct SettingsStatusRow: View {
    let title: String
    let value: String
    let symbol: String
    let color: Color

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol)
                .foregroundColor(color)
                .frame(width: 24)
            Text(title)
            Spacer()
            Text(value)
                .foregroundColor(.secondary)
            Image(systemName: "chevron.right")
                .font(.caption.bold())
                .foregroundColor(Color.secondary.opacity(0.55))
        }
    }
}
