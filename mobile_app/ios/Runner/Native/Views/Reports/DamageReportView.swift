import SwiftUI

/// Formulario nativo de reporte de daños estructurales e incidentes post-sismo.
public struct DamageReportView: View {
    public let preselectedEvent: SeismicEvent?
    public let showsCloseButton: Bool
    @Environment(\.dismiss) private var dismiss

    @State private var selectedSeverity: DamageSeverity = .minor
    @State private var selectedHazards: Set<ObservedHazard> = []
    @State private var peopleTrapped = false
    @State private var injuriesObserved = false
    @State private var safeToRemain = true
    @State private var comment = ""

    @State private var isSubmitting = false
    @State private var showSuccessAlert = false
    @State private var submissionMessage = ""
    @State private var showErrorAlert = false

    public init(preselectedEvent: SeismicEvent?, showsCloseButton: Bool = true) {
        self.preselectedEvent = preselectedEvent
        self.showsCloseButton = showsCloseButton
    }

    public var body: some View {
        CompatibleNavigationStack {
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
                    // Los siete peligros que ofrece la app de Android: un
                    // catálogo más corto en iPhone haría incomparables los
                    // reportes de una misma emergencia.
                    ForEach(ObservedHazard.allCases) { hazard in
                        Toggle(
                            hazard.title,
                            isOn: Binding(
                                get: { selectedHazards.contains(hazard) },
                                set: { isOn in
                                    if isOn {
                                        selectedHazards.insert(hazard)
                                    } else {
                                        selectedHazards.remove(hazard)
                                    }
                                }
                            )
                        )
                        .tint(SeismikColors.amber)
                    }
                    Toggle("Personas atrapadas", isOn: $peopleTrapped)
                        .tint(SeismikColors.crimson)
                    Toggle("Personas lesionadas", isOn: $injuriesObserved)
                        .tint(SeismikColors.crimson)
                    Toggle("¿Es seguro permanecer en el lugar?", isOn: $safeToRemain)
                        .tint(SeismikColors.emerald)
                }

                Section(header: Text("OBSERVACIONES Y UBICACIÓN EXACTA")) {
                    if #available(iOS 16.0, *) {
                        TextField("Detalles del inmueble o situación de riesgo...", text: $comment, axis: .vertical)
                            .lineLimit(3...5)
                    } else {
                        TextEditor(text: $comment)
                            .frame(minHeight: 80)
                    }
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
                ToolbarItem(placement: .navigationBarLeading) {
                    if showsCloseButton {
                        Button("Cancelar") {
                            dismiss()
                        }
                    }
                }
            }
            .alert("Reporte Transmitido", isPresented: $showSuccessAlert) {
                Button("Entendido") {
                    if showsCloseButton { dismiss() }
                }
            } message: {
                Text(submissionMessage)
            }
            .alert("No se pudo guardar el reporte", isPresented: $showErrorAlert) {
                Button("Aceptar", role: .cancel) {}
            } message: {
                Text(submissionMessage)
            }
        }
    }

    private func submitReport() {
        isSubmitting = true
        HapticManager.light()

        // El orden estable evita que dos reportes idénticos difieran sólo en
        // el orden de esta lista.
        let hazardsList = ObservedHazard.allCases
            .filter(selectedHazards.contains)
            .map(\.rawValue)

        let payload = DamageReportPayload(
            deviceId: SeismikAPIClient.shared.deviceId,
            earthquakeEventId: preselectedEvent?.id,
            officialEventId: preselectedEvent?.id,
            observedAt: ISO8601DateFormatter().string(from: Date()),
            latitude: LocationManager.shared.userCoordinate?.latitude ?? 4.65,
            longitude: LocationManager.shared.userCoordinate?.longitude ?? -74.05,
            countryCode: SeismikAPIClient.deviceCountryCode,
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
            await deliver { try await SeismikAPIClient.shared.submitDamageReport(payload) }
        }
    }

    /// Traduce el resultado del envío a lo que ve la persona.
    ///
    /// Antes se descartaba con `try?` y siempre se mostraba «recibido», incluso
    /// cuando el servidor había rechazado el reporte o no había red. Quien
    /// reporta daños necesita saber cuál de las tres cosas ocurrió.
    @MainActor
    private func deliver(_ send: () async throws -> ReportSubmission) async {
        defer { isSubmitting = false }
        do {
            switch try await send() {
            case let .sent(duplicate):
                submissionMessage = duplicate
                    ? "Este reporte ya estaba registrado. Gracias de todos modos."
                    : "Gracias por reportar. Tu información ayuda a estimar la intensidad real."
                HapticManager.success()
                showSuccessAlert = true
            case .queued:
                submissionMessage = "Sin conexión: el reporte quedó guardado en el iPhone "
                    + "y se enviará automáticamente cuando vuelva la red."
                HapticManager.success()
                showSuccessAlert = true
            }
            await SeismikState.shared.flushPendingReports()
        } catch {
            submissionMessage = error.localizedDescription
            HapticManager.error()
            showErrorAlert = true
        }
    }

}
