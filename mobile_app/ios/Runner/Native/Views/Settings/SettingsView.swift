import SwiftUI

/// Vista de configuración nativa en SwiftUI para Seismik en iOS.
public struct SettingsView: View {
    @ObservedObject var state: SeismikState
    @Environment(\.dismiss) private var dismiss

    public var body: some View {
        CompatibleNavigationStack {
            Form {
                Section(header: Text("ALERTAS SÍSMICAS")) {
                    Toggle("Alertas tempranas", isOn: $state.receiveEarlyAlerts)
                        .tint(SeismikColors.systemBlue)

                    Toggle("Actualizaciones oficiales", isOn: $state.receiveOfficialUpdates)
                        .tint(SeismikColors.systemBlue)

                    HStack {
                        Text("Magnitud mínima")
                        Spacer()
                        Text("M \(String(format: "%.1f", state.minMagnitude))")
                            .foregroundColor(.secondary)
                            .font(.system(.subheadline, design: .rounded))
                    }

                    Stepper(value: $state.minMagnitude, in: 2.0...7.0, step: 0.5) {
                        Text("Ajustar magnitud mínima")
                    }

                    HStack {
                        Text("Radio de alerta")
                        Spacer()
                        Text("\(Int(state.alertRadiusKm)) km")
                            .foregroundColor(.secondary)
                            .font(.system(.subheadline, design: .rounded))
                    }

                    Stepper(value: $state.alertRadiusKm, in: 50...1000, step: 50) {
                        Text("Ajustar radio de detección")
                    }

                    Button {
                        dismiss()
                        DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                            state.runAlertSimulation()
                        }
                    } label: {
                        HStack {
                            Image(systemName: "bell.badge.fill")
                                .foregroundColor(SeismikColors.crimson)
                            Text("Probar alerta en este iPhone")
                                .foregroundColor(.primary)
                        }
                    }
                }

                Section(header: Text("DISPOSITIVO Y PRIVACIDAD")) {
                    HStack {
                        Text("Identificador")
                        Spacer()
                        Text(String(SeismikAPIClient.shared.deviceId.prefix(12)) + "...")
                            .font(.system(.caption, design: .monospaced))
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Text("Ubicación GPS")
                        Spacer()
                        Text(LocationManager.shared.userCoordinate != nil ? "Activa" : "No disponible")
                            .foregroundColor(LocationManager.shared.userCoordinate != nil ? SeismikColors.emerald : .secondary)
                    }
                }

                Section(header: Text("ACERCA DE SEISMIK")) {
                    HStack {
                        Text("Versión")
                        Spacer()
                        Text("1.0.0 (26) · Apple Native")
                            .foregroundColor(.secondary)
                    }
                    HStack {
                        Text("Plataforma")
                        Spacer()
                        Text("SwiftUI + MapKit")
                            .foregroundColor(.secondary)
                    }
                }
            }
            .navigationTitle("Configuración")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Cerrar") {
                        dismiss()
                    }
                }
            }
        }
    }
}
