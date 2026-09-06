import SwiftUI

/// Formulario nativo de reporte ciudadano de sismo sentido (DYFI).
public struct FeltReportView: View {
    public let preselectedEvent: SeismicEvent?
    @Environment(\.dismiss) private var dismiss

    @State private var felt: Bool = true
    @State private var intensity: Double = 4.0
    @State private var indoors: Bool = true
    @State private var floorNumber: Int = 1
    @State private var wokeUp: Bool = false
    @State private var difficultyStanding: Bool = false
    @State private var objectsFell: Bool = false
    @State private var comment: String = ""

    @State private var isSubmitting: Bool = false
    @State private var showSuccessAlert: Bool = false

    private let intensities: [(mmi: Int, label: String, desc: String)] = [
        (1, "I · Instrumental", "Casi imperceptible."),
        (2, "II · Muy débil", "Sentido por pocas personas en reposo."),
        (3, "III · Débil", "Vibración leve, similar al paso de un camión."),
        (4, "IV · Moderado", "Objetos colgantes oscilan visiblemente."),
        (5, "V · Algo fuerte", "Sentido por la mayoría; líquidos se mueven."),
        (6, "VI · Fuerte", "Dificultad para caminar; caída de adornos."),
        (7, "VII · Muy fuerte", "Daño leve en edificaciones de buen diseño."),
        (8, "VIII · Destructivo", "Daño considerable en estructuras ordinarias."),
        (9, "IX · Ruinoso", "Pánico generalizado; grietas en el suelo."),
        (10, "X · Desastroso", "Destrucción de la mayoría de obras de mampostería.")
    ]

    public var body: some View {
        NavigationStack {
            Form {
                Section(header: Text("PERCEPCIÓN")) {
                    Toggle("¿Sentiste el movimiento?", isOn: $felt)
                        .tint(SeismikColors.emerald)

                    if felt {
                        VStack(alignment: .leading, spacing: 8) {
                            HStack {
                                Text("Intensidad percibida")
                                Spacer()
                                Text(currentIntensityInfo.label)
                                    .font(.system(.subheadline, design: .rounded).bold())
                                    .foregroundColor(SeismikColors.amber)
                            }

                            Slider(
                                value: $intensity,
                                in: 1...10,
                                step: 1
                            ) {
                                Text("Intensidad")
                            }
                            .tint(SeismikColors.amber)
                            .onChange(of: intensity) { _ in
                                HapticManager.selection()
                            }

                            Text(currentIntensityInfo.desc)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 4)
                    }
                }

                if felt {
                    Section(header: Text("SITUACIÓN Y ENTORNO")) {
                        Toggle("¿Estabas en el interior de una edificación?", isOn: $indoors)
                            .tint(SeismikColors.systemBlue)

                        if indoors {
                            Stepper("Piso: \(floorNumber)", value: $floorNumber, in: -5...100)
                        }

                        Toggle("¿El sismo te despertó?", isOn: $wokeUp)
                        Toggle("¿Dificultad para mantenerte en pie?", isOn: $difficultyStanding)
                        Toggle("¿Cayeron objetos de estantes o paredes?", isOn: $objectsFell)
                    }

                    Section(header: Text("COMENTARIOS ADICIONALES")) {
                        TextField("Describe brevemente lo que observaste...", text: $comment, axis: .vertical)
                            .lineLimit(3...5)
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
                                Text("Enviar Reporte Ciudadano")
                                    .font(.system(size: 16, weight: .bold))
                            }
                            Spacer()
                        }
                    }
                    .disabled(isSubmitting)
                }
            }
            .navigationTitle("¿Sentiste el Sismo?")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarLeading) {
                    Button("Cancelar") {
                        dismiss()
                    }
                }
            }
            .alert("Reporte Recibido", isPresented: $showSuccessAlert) {
                Button("Entendido") { dismiss() }
            } message: {
                Text("Gracias por tu colaboración. Tu aporte fortalece el mapa de intensidad sísmica comunitaria.")
            }
        }
    }

    private var currentIntensityInfo: (mmi: Int, label: String, desc: String) {
        let index = max(0, min(Int(intensity) - 1, intensities.count - 1))
        return intensities[index]
    }

    private func submitReport() {
        isSubmitting = true
        HapticManager.light()

        let payload = FeltReportPayload(
            deviceId: SeismikAPIClient.shared.deviceId,
            earthquakeEventId: preselectedEvent?.id,
            officialEventId: preselectedEvent?.id,
            observedAt: ISO8601DateFormatter().string(from: Date()),
            latitude: LocationManager.shared.userCoordinate?.latitude ?? 4.65,
            longitude: LocationManager.shared.userCoordinate?.longitude ?? -74.05,
            countryCode: "CO",
            felt: felt,
            intensityMmi: felt ? Int(intensity) : nil,
            indoors: indoors,
            floor: indoors ? floorNumber : nil,
            wokeUp: wokeUp,
            difficultyStanding: difficultyStanding,
            objectsMoved: nil,
            objectsFell: objectsFell,
            visibleDamage: nil,
            comment: comment.isEmpty ? nil : comment
        )

        Task {
            _ = try? await SeismikAPIClient.shared.submitFeltReport(payload)
            isSubmitting = false
            HapticManager.success()
            showSuccessAlert = true
        }
    }
}
