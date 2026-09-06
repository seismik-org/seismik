import SwiftUI

/// Formulario nativo de reporte de daños estructurales e incidentes post-sismo.
public struct DamageReportView: View {
    public let preselectedEvent: SeismicEvent?
    @Environment(\.dismiss) private var dismiss

    @State private var selectedSeverity: DamageSeverity = .light
    @State private var gasLeak = false
    @State private var electricalHazard = false
    @State private var peopleTrapped = false
    @State private var injuriesObserved = false
    @State private var safeToRemain = true
    @State private var comment = ""

    @State private var isSubmitting = false
    @State private var showSuccessAlert = false

    public var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("SEVERIDAD DE DAÑOS")) {
                    ForEach(DamageSeverity.allCases) { severity in
                        HStack {
                            Text(severity.title)
                                .foregroundColor(.primary)
                            Spacer()
                            if selectedSeverity == severity {
                                Image(systemName: "checkmark")
                                    .foregroundColor(SeismikColors.crimson)
                                    .font(.system(size: 14, weight: .bold))
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            HapticManager.selection()
                            selectedSeverity = severity
                        }
                    }
                }

                Section(header: Text("PELIGROS E INTEGRIDAD")) {
                    Toggle("Fuga de gas o olor persistente", isOn: $gasLeak)
                        .tint(SeismikColors.amber)
                    Toggle("Cables caídos o riesgo eléctrico", isOn: $electricalHazard)
                        .tint(SeismikColors.amber)
                    Toggle("Personas atrapadas", isOn: $peopleTrapped)
                        .tint(SeismikColors.crimson)
                    Toggle("Personas lesionadas", isOn: $injuriesObserved)
                        .tint(SeismikColors.crimson)
                    Toggle("¿Es seguro permanecer en el lugar?", isOn: $safeToRemain)
                        .tint(SeismikColors.emerald)
                }

                Section(header: Text("OBSERVACIONES Y UBICACIÓN EXACTA")) {
                    TextField("Detalles del inmueble o situación de riesgo...", text: $comment, axis: .vertical)
                        .lineLimit(3...5)
                }

                Section {
                    Button {
                        submitReport()
                    } label: {
                        HStack {
                            Spacer()
                            if isSubmitting {
                                ProgressView()
                            } else {
                                Text("Enviar Reporte de Daños")
                                    .font(.system(size: 16, weight: .bold))
                                    .foregroundColor(SeismikColors.crimson)
                            }
                            Spacer()
                        }
                    }
                    .disabled(isSubmitting)
                }
            }
            .navigationTitle("Reporte de Daños")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancelar") {
                        dismiss()
                    }
                }
            }
            .alert("Reporte Transmitido", isPresented: $showSuccessAlert) {
                Button("Entendido") { dismiss() }
            } message: {
                Text("La información ha sido canalizada. Si hay vidas en peligro inminente, llama al número local de emergencias (123).")
            }
        }
    }

    private func submitReport() {
        isSubmitting = true
        HapticManager.light()

        var hazardsList: [String] = []
        if gasLeak { hazardsList.append("gas_leak") }
        if electricalHazard { hazardsList.append("electrical_hazard") }

        let payload = DamageReportPayload(
            deviceId: SeismikAPIClient.shared.deviceId,
            earthquakeEventId: preselectedEvent?.id,
            officialEventId: preselectedEvent?.id,
            observedAt: ISO8601DateFormatter().string(from: Date()),
            latitude: LocationManager.shared.userCoordinate?.latitude ?? 4.65,
            longitude: LocationManager.shared.userCoordinate?.longitude ?? -74.05,
            countryCode: "CO",
            severity: selectedSeverity.rawValue,
            hazards: hazardsList,
            buildingType: nil,
            peopleTrapped: peopleTrapped,
            injuriesObserved: injuriesObserved,
            emergencyServicesContacted: false,
            safeToRemain: safeToRemain,
            comment: comment.isEmpty ? nil : comment
        )

        Task {
            _ = try? await SeismikAPIClient.shared.submitDamageReport(payload)
            isSubmitting = false
            HapticManager.success()
            showSuccessAlert = true
        }
    }
}
