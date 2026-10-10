import SwiftUI

/// Formulario nativo de reporte ciudadano de sismo sentido (DYFI).
public struct FeltReportView: View {
    public let preselectedEvent: SeismicEvent?
    public let showsCloseButton: Bool
    @Environment(\.dismiss) private var dismiss

    @State private var felt: Bool?
    @State private var selectedEvent: SeismicEvent?
    @State private var intensity: Double = 4.0
    @State private var indoors: Bool = true
    @State private var floorNumber: Int = 1
    @State private var wokeUp: Bool = false
    @State private var difficultyStanding: Bool = false
    @State private var objectsFell: Bool = false
    @State private var comment: String = ""

    @State private var isSubmitting: Bool = false
    @State private var showSuccessAlert: Bool = false
    @State private var submissionMessage: String = ""
    @State private var showErrorAlert: Bool = false

    public init(preselectedEvent: SeismicEvent?, showsCloseButton: Bool = true) {
        self.preselectedEvent = preselectedEvent
        self.showsCloseButton = showsCloseButton
    }

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
        CompatibleNavigationStack {
            Form {
                ReportEventSelection(selectedEvent: $selectedEvent, suggested: preselectedEvent)
                    .disabled(isSubmitting)
                Section(header: Text("PERCEPCIÓN")) {
                    Picker("¿Lo sentiste?", selection: $felt) {
                        Text("Selecciona una respuesta").tag(Bool?.none)
                        Text("Sí, lo sentí").tag(Optional(true))
                        Text("No lo sentí").tag(Optional(false))
                    }
                    .disabled(selectedEvent == nil || isSubmitting)

                    if felt == true {
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

                if felt == true {
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
                        if #available(iOS 16.0, *) {
                            TextField("Describe brevemente lo que observaste...", text: $comment, axis: .vertical)
                                .lineLimit(3...5)
                        } else {
                            TextEditor(text: $comment)
                                .frame(minHeight: 80)
                        }
                    }
                }

            }
            .safeAreaInset(edge: .bottom, spacing: 0) {
                reportButton
            }
            .navigationTitle("¿Sentiste el Sismo?")
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
            .alert("Reporte Recibido", isPresented: $showSuccessAlert) {
                Button("Entendido") {
                    selectedEvent = nil
                    felt = nil
                    if showsCloseButton { dismiss() }
                }
            } message: {
                Text(submissionMessage)
            }
            .onChange(of: selectedEvent?.id) { _ in felt = nil }
            .alert("No se pudo guardar el reporte", isPresented: $showErrorAlert) {
                Button("Aceptar", role: .cancel) {}
            } message: {
                Text(submissionMessage)
            }
        }
    }

    private var reportButton: some View {
        Button(action: submitReport) {
            HStack(spacing: 10) {
                if isSubmitting { ProgressView() }
                Text(isSubmitting ? "Enviando…" : "Enviar reporte")
                    .font(.headline)
            }
            .frame(maxWidth: .infinity, minHeight: 50)
        }
        .buttonStyle(.borderedProminent)
        .disabled(isSubmitting || selectedEvent == nil || felt == nil)
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(.bar)
        .accessibilityHint("Envía este reporte a Seismik")
    }

    private var currentIntensityInfo: (mmi: Int, label: String, desc: String) {
        let index = max(0, min(Int(intensity) - 1, intensities.count - 1))
        return intensities[index]
    }

    private func submitReport() {
        guard let selectedEvent, let felt else { return }
        guard let coordinate = LocationManager.shared.userCoordinate else {
            submissionMessage = "Se necesita tu ubicación para asociar el reporte al lugar correcto. Activa la ubicación de Seismik en Ajustes e inténtalo de nuevo."
            HapticManager.error()
            showErrorAlert = true
            return
        }
        isSubmitting = true
        HapticManager.light()

        let payload = FeltReportPayload(
            deviceId: SeismikAPIClient.shared.deviceId,
            earthquakeEventId: selectedEvent.id,
            officialEventId: selectedEvent.officialEventId,
            observedAt: ISO8601DateFormatter().string(from: Date()),
            latitude: coordinate.latitude,
            longitude: coordinate.longitude,
            locationPrecision: SeismikState.shared.preciseLocationByDefault ? "precise" : "approximate",
            countryCode: SeismikAPIClient.deviceCountryCode,
            felt: felt,
            intensityMmi: felt ? Int(intensity) : nil,
            indoors: indoors,
            floor: indoors ? floorNumber : nil,
            wokeUp: felt && wokeUp,
            difficultyStanding: felt && difficultyStanding,
            objectsMoved: nil,
            objectsFell: felt && objectsFell,
            visibleDamage: nil,
            comment: comment.isEmpty ? nil : comment
        )

        Task {
            await deliver { try await SeismikAPIClient.shared.submitFeltReport(payload) }
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

/// Location only ranks candidates. The person must choose the event explicitly.
struct ReportEventSelection: View {
    @Binding var selectedEvent: SeismicEvent?
    let suggested: SeismicEvent?
    @ObservedObject private var location = LocationManager.shared
    @State private var events: [SeismicEvent] = []
    @State private var showing = false
    @State private var loading = false
    @State private var warning: String?

    private var choices: [SeismicEvent] {
        ReportEventChoices.ordered(events + (suggested.map { [$0] } ?? []),
                                   at: location.currentCoordinate, now: Date())
    }

    var body: some View {
        Section(header: Text("SELECCIONA EL SISMO")) {
            if let selectedEvent { Text(label(selectedEvent)) }
            Button(selectedEvent == nil ? "Elegir sismo" : "Cambiar sismo") {
                location.requestPermission()
                showing = true
            }
            Text("Verifica lugar y hora. Se ordenan por distancia a tu ubicación actual; cercanía no significa que lo hayas sentido.")
                .font(.caption).foregroundColor(.secondary)
        }
        .sheet(isPresented: $showing) {
            CompatibleNavigationStack {
                List {
                    if loading { ProgressView("Buscando sismos…") }
                    if location.currentCoordinate == nil {
                        Text("Sin ubicación: se ordenan por fecha. Activa la ubicación para ver los más cercanos.")
                    }
                    if let warning { Text(warning).foregroundColor(.secondary) }
                    if !loading && choices.isEmpty { Text("No hay sismos recientes disponibles. No se enviará un reporte sin sismo.") }
                    ForEach(choices) { event in
                        Button {
                            selectedEvent = event
                            showing = false
                        } label: {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(label(event)).foregroundColor(.primary)
                                Text(event.agency ?? "Seismik · preliminar").font(.caption).foregroundColor(.secondary)
                            }
                        }
                    }
                }
                .navigationTitle("Sismos · últimos 7 días")
                .toolbar {
                    ToolbarItem(placement: .navigationBarLeading) { Button("Cancelar") { showing = false } }
                    ToolbarItem(placement: .navigationBarTrailing) {
                        Button("Actualizar") { location.requestPermission(); Task { await refresh() } }.disabled(loading)
                    }
                }
                .task { await refresh() }
            }
        }
    }

    private func label(_ event: SeismicEvent) -> String {
        let time = event.detectedAt.map { DateFormatter.localizedString(from: $0, dateStyle: .short, timeStyle: .short) } ?? "Hora no disponible"
        let magnitude = event.magnitude.map { String(format: " · M%.1f", $0) } ?? ""
        let distance = ReportEventChoices.distance(event, from: location.currentCoordinate).map { " · \(Int($0.rounded())) km de tu ubicación" } ?? ""
        return "\(event.place ?? "Ubicación no determinada") · \(time)\(magnitude)\(distance)"
    }

    @MainActor private func refresh() async {
        loading = true
        warning = nil
        defer { loading = false }
        do { events = try await SeismikAPIClient.shared.fetchRecentEvents(days: 7, minimumMagnitude: 0) }
        catch { events = SeismikState.shared.events; warning = "Sin conexión: se muestran los sismos guardados." }
    }
}
