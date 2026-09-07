import CoreLocation
import SwiftUI
import UIKit
import UserNotifications

/// Preferencias completas de Seismik en iOS con 100% de paridad con Android.
public struct SettingsView: View {
    @ObservedObject var state: SeismikState
    public let showsCloseButton: Bool
    @ObservedObject private var locationManager = LocationManager.shared
    @Environment(\.dismiss) private var dismiss

    @State private var notificationStatus: UNAuthorizationStatus = .notDetermined
    @State private var showCopiedAlert = false

    public init(state: SeismikState, showsCloseButton: Bool = true) {
        self.state = state
        self.showsCloseButton = showsCloseButton
    }

    public var body: some View {
        CompatibleNavigationStack {
            Form {
                // Encabezado de Identidad y Versión
                Section {
                    HStack(spacing: 14) {
                        Image("AppLogo")
                            .resizable()
                            .scaledToFit()
                            .frame(width: 52, height: 52)
                            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))

                        VStack(alignment: .leading, spacing: 3) {
                            Text("Seismik")
                                .font(.system(size: 22, weight: .bold, design: .rounded))
                                .foregroundColor(.primary)

                            Text("Versión 1.0.0 (Build 28)")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                                .foregroundColor(SeismikColors.systemBlue)

                            Text("Beta experimental")
                                .font(.system(size: 12, weight: .regular))
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }

                // Alertas críticas (Pantalla completa, simulacro, magnitudes y radio)
                Section(header: Text("Alertas críticas")) {
                    Button(action: openSystemSettings) {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Autorizar pantalla completa / Alertas")
                                    .font(.body)
                                    .foregroundColor(.primary)
                                Text("Necesario para abrir la guía con pantalla bloqueada y emitir alertas críticas.")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Image(systemName: "arrow.up.right.square")
                                .font(.system(size: 16))
                                .foregroundColor(SeismikColors.systemBlue)
                        }
                    }

                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Probar alerta en este teléfono")
                                .font(.body)
                                .foregroundColor(.primary)
                            Text("Ejecuta una simulación local. No reporta un sismo ni avisa a otros usuarios.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                        Button(action: runAlertTest) {
                            Image(systemName: "play.fill")
                                .font(.system(size: 15))
                                .foregroundColor(.white)
                                .frame(width: 36, height: 36)
                                .background(Circle().fill(SeismikColors.crimson))
                        }
                        .buttonStyle(.plain)
                    }

                    Toggle(isOn: $state.receiveEarlyAlerts) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Alertas tempranas")
                                .font(.body)
                            Text("Avisos técnicos multiestación cercanos. Pueden llegar antes del reporte oficial.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .tint(SeismikColors.systemBlue)
                    .onChange(of: state.receiveEarlyAlerts) { _ in synchronizePreferences() }

                    Toggle(isOn: $state.receiveOfficialUpdates) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Actualizaciones oficiales")
                                .font(.body)
                            Text("Magnitud, profundidad y fuente publicada por una entidad geológica.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .tint(SeismikColors.systemBlue)
                    .onChange(of: state.receiveOfficialUpdates) { _ in synchronizePreferences() }

                    // Deslizador continuo de magnitud mínima para alerta
                    SliderRow(
                        title: "Magnitud mínima para aviso oficial",
                        value: $state.minimumNotificationMagnitude,
                        range: 2.0...8.0,
                        step: 0.5,
                        format: "%.1f",
                        prefix: "M"
                    ) {
                        synchronizePreferences()
                    }

                    // Chips interactivos de radio de cercanía (idénticos a Android)
                    ProximityRadiusChipsView(selectedRadius: $state.alertRadiusKm) {
                        synchronizePreferences()
                    }
                }

                // Mapas y sincronización
                Section(header: Text("Mapas y sincronización")) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Abrir epicentros con")
                            .font(.body)
                        Text("Se usa al tocar «Abrir epicentro» en un sismo. Si la app elegida no está instalada, se abre la versión web.")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        HStack {
                            Text("Aplicación:")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            Spacer()
                            Picker("Abrir epicentros con", selection: $state.mapProvider) {
                                Text("Según el sistema").tag("system")
                                Text("Apple Maps").tag("apple")
                                Text("Google Maps").tag("google")
                                Text("OpenStreetMap").tag("osm")
                            }
                            .pickerStyle(.menu)
                        }
                        .padding(.top, 4)
                    }
                    .padding(.vertical, 4)

                    Picker("Estilo de mapa en la app", selection: $state.appMapType) {
                        Text("Estándar").tag("standard")
                        Text("Satélite").tag("satellite")
                        Text("Híbrido").tag("hybrid")
                    }

                    HStack(spacing: 12) {
                        Image(systemName: "icloud")
                            .foregroundColor(.secondary)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Reportes sin enviar")
                                .font(.body)
                            Text(state.pendingReportCount > 0
                                 ? "\(state.pendingReportCount) reportes pendientes de sincronizar."
                                 : "No hay reportes pendientes.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        Spacer()
                    }
                }

                // Historial sísmico (Slider de magnitud, periodo y fuentes)
                Section(header: Text("Historial sísmico")) {
                    SliderRow(
                        title: "Magnitud mínima del historial",
                        value: $state.minMagnitude,
                        range: 0.0...7.0,
                        step: 0.5,
                        format: "%.1f",
                        prefix: "M"
                    ) {
                        refreshHistory()
                    }

                    Picker("Periodo del historial", selection: $state.historyDays) {
                        Text("24 horas").tag(1)
                        Text("7 días").tag(7)
                        Text("14 días").tag(14)
                        Text("30 días").tag(30)
                    }
                    .onChange(of: state.historyDays) { _ in refreshHistory() }

                    Toggle("Incluir detecciones preliminares", isOn: $state.includePreliminaryEvents)
                        .onChange(of: state.includePreliminaryEvents) { _ in refreshHistory() }

                    Text("Fuentes del historial")
                        .font(.system(size: 15, weight: .bold))
                        .padding(.top, 4)

                    HistorySourceRow(
                        title: "SGC · Colombia",
                        subtitle: "Servicio Geológico Colombiano",
                        isActive: state.isSourceActive("sgc_colombia")
                    ) {
                        state.toggleSource("sgc_colombia")
                    }

                    HistorySourceRow(
                        title: "USGS · Global",
                        subtitle: "Cobertura mundial de respaldo",
                        isActive: state.isSourceActive("usgs_global")
                    ) {
                        state.toggleSource("usgs_global")
                    }

                    HistorySourceRow(
                        title: "Seismik / SeedLink · Preliminar",
                        subtitle: "Detección automática STA/LTA multiestación.",
                        isActive: state.isSourceActive("seismik_seedlink_preliminary")
                    ) {
                        state.toggleSource("seismik_seedlink_preliminary")
                    }

                    HistorySourceRow(
                        title: "IGP · Perú",
                        subtitle: nil,
                        isActive: state.isSourceActive("igp_peru")
                    ) {
                        state.toggleSource("igp_peru")
                    }

                    HistorySourceRow(
                        title: "INGV · Italia",
                        subtitle: nil,
                        isActive: state.isSourceActive("ingv_italy")
                    ) {
                        state.toggleSource("ingv_italy")
                    }

                    HistorySourceRow(
                        title: "GeoNet · Nueva Zelanda",
                        subtitle: nil,
                        isActive: state.isSourceActive("geonet_new_zealand")
                    ) {
                        state.toggleSource("geonet_new_zealand")
                    }

                    HistorySourceRow(
                        title: "BMKG · Indonesia",
                        subtitle: nil,
                        isActive: state.isSourceActive("bmkg_indonesia")
                    ) {
                        state.toggleSource("bmkg_indonesia")
                    }

                    HistorySourceRow(
                        title: "JMA · Japón",
                        subtitle: nil,
                        isActive: state.isSourceActive("jma_japan")
                    ) {
                        state.toggleSource("jma_japan")
                    }
                }

                // Privacidad y sensores
                Section(header: Text("Privacidad y sensores")) {
                    Toggle(isOn: $state.crowdsourcingEnabled) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Detección colaborativa")
                                .font(.body)
                            Text("Activa o detiene realmente el acelerómetro de Seismik.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .tint(SeismikColors.systemBlue)

                    Toggle(isOn: $state.preciseLocationByDefault) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Ubicación precisa en reportes")
                                .font(.body)
                            Text("Desactivada por defecto: se conserva una ubicación aproximada.")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                    .tint(SeismikColors.systemBlue)

                    Button(action: openSystemSettings) {
                        HStack(spacing: 12) {
                            Image(systemName: "shield.lefthalf.filled")
                                .foregroundColor(SeismikColors.systemBlue)
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Permisos del sistema")
                                    .font(.body)
                                    .foregroundColor(.primary)
                                Text("Ubicación, sensores y notificaciones")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Spacer()
                            Image(systemName: "arrow.up.right.square")
                                .foregroundColor(.secondary)
                        }
                    }
                }

                // Diagnóstico de la beta
                Section(
                    header: Text("Diagnóstico de la beta"),
                    footer: Text("Este identificador permite incluir el teléfono en la lista cerrada de pruebas push. No es un dato personal.")
                ) {
                    HStack {
                        VStack(alignment: .leading, spacing: 3) {
                            Text("Identificador de este dispositivo")
                                .font(.body)
                            Text(state.deviceId)
                                .font(.system(.caption, design: .monospaced))
                                .foregroundColor(.secondary)
                                .lineLimit(1)
                        }
                        Spacer()
                        Button {
                            UIPasteboard.general.string = state.deviceId
                            HapticManager.selection()
                            showCopiedAlert = true
                        } label: {
                            Image(systemName: "doc.on.doc")
                                .font(.system(size: 16))
                                .foregroundColor(SeismikColors.systemBlue)
                        }
                        .buttonStyle(.plain)
                    }
                }

                // Acerca de Seismik
                Section(header: Text("Acerca de Seismik")) {
                    SettingsValueRow(title: "Versión", value: versionDescription)
                    SettingsValueRow(title: "Motor de mapa", value: "Apple MapKit")
                    Link("Privacidad", destination: URL(string: "https://seismik.org/terms-of-privacy")!)
                    Link("Términos del servicio", destination: URL(string: "https://seismik.org/terms-of-service")!)
                }

                // Nota legal y pie de página idéntico a Android
                Section {
                    Text("Los cambios quedan guardados en el teléfono y se aplican inmediatamente. Seismik continúa en beta experimental y no sustituye a las autoridades.")
                        .font(.footnote)
                        .foregroundColor(.secondary)
                        .listRowBackground(Color.clear)
                }
            }
            .navigationTitle("Configuración")
            .navigationBarTitleDisplayMode(.large)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if showsCloseButton {
                        Button("Listo") { dismiss() }
                    }
                }
            }
            .alert("Copiado", isPresented: $showCopiedAlert) {
                Button("Aceptar", role: .cancel) {}
            } message: {
                Text("Identificador del dispositivo copiado al portapapeles.")
            }
            .task {
                notificationStatus = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
            }
        }
    }

    private var versionDescription: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "0.6.6"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "27"
        return "\(version) (\(build))"
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

// MARK: - Componentes Auxiliares de Configuración

private struct SliderRow: View {
    let title: String
    @Binding var value: Double
    let range: ClosedRange<Double>
    let step: Double
    let format: String
    let prefix: String
    let onChange: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(title)
                    .font(.body)
                Spacer()
                Text("\(prefix) \(String(format: format, value))")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundColor(SeismikColors.systemBlue)
            }

            Slider(value: $value, in: range, step: step) {
                Text(title)
            } onEditingChanged: { ended in
                if ended {
                    HapticManager.selection()
                    onChange()
                }
            }
            .tint(SeismikColors.systemBlue)
        }
        .padding(.vertical, 4)
    }
}

private struct ProximityRadiusChipsView: View {
    @Binding var selectedRadius: Double
    let onChange: () -> Void

    let radii: [Double] = [50, 100, 150, 250, 400, 600]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Umbral de cercanía")
                .font(.body)

            LazyVGrid(columns: [GridItem(.adaptive(minimum: 85), spacing: 8)], spacing: 8) {
                ForEach(radii, id: \.self) { r in
                    let isSelected = Int(selectedRadius) == Int(r)
                    Button {
                        selectedRadius = r
                        HapticManager.selection()
                        onChange()
                    } label: {
                        HStack(spacing: 4) {
                            if isSelected {
                                Image(systemName: "checkmark")
                                    .font(.system(size: 11, weight: .bold))
                            }
                            Text("\(Int(r)) km")
                                .font(.system(size: 13, weight: isSelected ? .bold : .medium))
                        }
                        .foregroundColor(isSelected ? .white : .primary)
                        .padding(.vertical, 8)
                        .padding(.horizontal, 12)
                        .frame(maxWidth: .infinity)
                        .background(
                            RoundedRectangle(cornerRadius: 10, style: .continuous)
                                .fill(isSelected ? SeismikColors.systemBlue : Color.secondary.opacity(0.12))
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(.vertical, 4)
    }
}

private struct HistorySourceRow: View {
    let title: String
    let subtitle: String?
    let isActive: Bool
    let onToggle: () -> Void

    var body: some View {
        Button(action: onToggle) {
            HStack(alignment: .top, spacing: 12) {
                Image(systemName: isActive ? "checkmark.square.fill" : "square")
                    .foregroundColor(isActive ? SeismikColors.systemBlue : .secondary)
                    .font(.system(size: 18))
                    .padding(.top, 2)

                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.body)
                        .foregroundColor(.primary)
                    if let subtitle = subtitle {
                        Text(subtitle)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                Spacer()
            }
        }
        .buttonStyle(.plain)
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
