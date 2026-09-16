import SwiftUI
import MapKit

/// Vista detallada del reporte sísmico con fidelidad total entre Reportes Oficiales y Preliminares (SeedLink).
public struct EventDetailView: View {
    public let event: SeismicEvent
    @Environment(\.dismiss) private var dismiss
    @AppStorage("seismik.map_provider") private var mapProvider = MapProviderChoice.apple.rawValue

    @State private var showFeltReport = false
    @State private var showDamageReport = false
    @State private var browserDestination: BrowserDestination?
    @ObservedObject private var locationManager = LocationManager.shared

    public init(event: SeismicEvent) {
        self.event = event
    }

    public var body: some View {
        CompatibleNavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    // 1. Banner de aviso preliminar (si aplica)
                    if event.isPreliminary {
                        preliminaryWarningBanner
                    }

                    // 2. Hero de Magnitud y Ubicación
                    magnitudeHeaderSection

                    // 3. Alerta de Tsunami si aplica
                    if event.tsunamiWarning {
                        tsunamiWarningBanner
                    }

                    // 4. Cuadrícula de Métricas
                    metricsGridSection

                    // 5. Coincidencia Multiestación STA/LTA (si preliminar con estaciones)
                    if event.isPreliminary && !event.stations.isEmpty {
                        multistationSection
                    }

                    // 6. Mini Mapa del Epicentro
                    if let coord = event.coordinate {
                        epicenterMapSection(coord)
                    }
                    perimeterCard

                    // 7. Botones de Acción Ciudadana y Mapas
                    actionButtonsSection

                    // 8. Pasos de Seguridad
                    safetySection
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .padding(.bottom, 36)
            }
            .navigationTitle(event.isPreliminary ? "Reporte preliminar" : "Reporte oficial")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Listo") {
                        HapticManager.selection()
                        dismiss()
                    }
                }
            }
            .sheet(isPresented: $showFeltReport) {
                FeltReportView(preselectedEvent: event)
            }
            .sheet(isPresented: $showDamageReport) {
                DamageReportView(preselectedEvent: event)
            }
            .sheet(item: $browserDestination) { destination in
                InAppBrowserView(url: destination.url)
                    .ignoresSafeArea()
            }
        }
        .modalSheetPresentation()
    }

    // MARK: - Subvistas

    private var preliminaryWarningBanner: some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 18, weight: .bold))
                .foregroundColor(SeismikColors.lavender)
                .padding(.top, 2)

            VStack(alignment: .leading, spacing: 5) {
                Text("SEISMIK / SEEDLINK · PRELIMINAR")
                    .font(.system(size: 11, weight: .bold, design: .rounded))
                    .tracking(0.6)
                    .foregroundColor(SeismikColors.lavender)

                Text("Detección automática multiestación. No es una confirmación oficial. Las ondas se miden en cada estación, pero una magnitud solo se mostrará tras calibrar su respuesta instrumental y validarla científicamente.")
                    .font(.system(size: 12.5))
                    .foregroundColor(.primary.opacity(0.88))
                    .lineSpacing(2.5)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .liquidGlass(cornerRadius: 16, tint: SeismikColors.lavender)
    }

    private var magnitudeHeaderSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            if event.isPreliminary && event.magnitude == nil {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("—")
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                        .foregroundColor(.primary)

                    Text("M")
                        .font(.system(size: 24, weight: .semibold, design: .rounded))
                        .foregroundColor(.secondary)
                }

                Text(event.place ?? (event.zoneId.map { "Zona técnica \($0)" } ?? "Zona técnica CO"))
                    .font(.system(size: 22, weight: .bold))
                    .foregroundColor(.primary)
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(event.magnitude.map { String(format: "%.1f", $0) } ?? "—")
                        .font(.system(size: 56, weight: .bold, design: .rounded))
                        .foregroundColor(.primary)

                    Text(event.magnitudeType ?? "M")
                        .font(.system(size: 22, weight: .semibold, design: .rounded))
                        .foregroundColor(.secondary)
                }

                Text(event.place ?? "Epicentro no determinado")
                    .font(.system(size: 20, weight: .bold))
                    .foregroundColor(.primary)
            }
        }
        .padding(.vertical, 4)
    }

    private var tsunamiWarningBanner: some View {
        HStack(spacing: 12) {
            Image(systemName: "wave.3.right")
                .font(.system(size: 22, weight: .bold))
                .foregroundColor(SeismikColors.crimson)
            VStack(alignment: .leading, spacing: 2) {
                Text("ALERTA DE TSUNAMI EMITIDA")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(SeismikColors.crimson)
                Text("Evacúe inmediatamente zonas costeras bajas.")
                    .font(.system(size: 12))
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
        .padding(14)
        .liquidGlass(cornerRadius: 18, tint: SeismikColors.crimson)
    }

    private var metricsGridSection: some View {
        LazyVGrid(columns: [GridItem(.flexible(), alignment: .topLeading), GridItem(.flexible(), alignment: .topLeading)], spacing: 16) {
            if event.isPreliminary {
                let stationCountText = event.stationCount.map { "\($0) estaciones" } ?? (event.stations.isEmpty ? "Multiestación" : "\(event.stations.count) estaciones")
                DetailedMetricCard(
                    icon: "arrow.down.to.line",
                    value: stationCountText,
                    label: "Coincidencia"
                )

                DetailedMetricCard(
                    icon: "checkmark.seal",
                    value: event.reviewStatus ?? "preliminar - sin revisión humana",
                    label: "Estado oficial"
                )

                DetailedMetricCard(
                    icon: "globe",
                    value: event.agencyDisplayName,
                    label: "Proveedor"
                )

                DetailedMetricCard(
                    icon: "clock",
                    value: event.utcTimeFormatted,
                    label: "Hora UTC"
                )

                if let window = event.coincidenceWindowSeconds {
                    DetailedMetricCard(
                        icon: "stopwatch",
                        value: String(format: "%.1f s", window),
                        label: "Ventana de coincidencia"
                    )
                }

                if let wave = event.waveStrengthIndex {
                    DetailedMetricCard(
                        icon: "waveform",
                        value: String(format: "%.2f", wave),
                        label: "Índice de onda (S/R)"
                    )
                }
            } else {
                DetailedMetricCard(
                    icon: "arrow.down.to.line",
                    value: event.depthKm.map { String(format: "%.1f km", $0) } ?? "No disponible",
                    label: "Profundidad"
                )

                DetailedMetricCard(
                    icon: "checkmark.seal",
                    value: event.reviewStatus ?? "automatic",
                    label: "Estado oficial"
                )

                DetailedMetricCard(
                    icon: "globe",
                    value: event.agencyDisplayName,
                    label: "Entidad emisora"
                )

                DetailedMetricCard(
                    icon: "clock",
                    value: event.utcTimeFormatted,
                    label: "Hora UTC"
                )
            }
        }
        .padding(.vertical, 6)
    }

    private var multistationSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("STA/LTA con coincidencia multiestación")
                .font(.system(size: 16, weight: .bold))
                .foregroundColor(.primary)

            let zone = event.zoneId ?? "CO"
            let countries = event.countryCodes.isEmpty ? "CO" : event.countryCodes.joined(separator: ", ")
            Text("Zona: \(zone) · Países: \(countries)")
                .font(.system(size: 13, weight: .medium))
                .foregroundColor(.secondary)

            Text("Magnitud aproximada: pendiente de calibración por estación. Mostrar un número sin esa calibración sería engañoso.")
                .font(.system(size: 12))
                .foregroundColor(.secondary)
                .lineSpacing(2)
                .padding(.bottom, 4)

            ForEach(event.stations) { st in
                HStack(spacing: 12) {
                    Image(systemName: "antenna.radiowaves.left.and.right")
                        .font(.system(size: 16))
                        .foregroundColor(SeismikColors.lavender)

                    VStack(alignment: .leading, spacing: 3) {
                        Text(st.stationId)
                            .font(.system(size: 14, weight: .bold))
                            .foregroundColor(.primary)
                        Text("\(st.providerId) · \(st.countryCode ?? "—") · \(st.triggerTimeFormatted)")
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    VStack(alignment: .trailing, spacing: 3) {
                        Text(String(format: "STA/LTA %.1f", st.staLtaRatio))
                            .font(.system(size: 12, weight: .semibold, design: .monospaced))
                            .foregroundColor(.primary)
                        Text(st.peakAmplitudeFormatted)
                            .font(.system(size: 11, design: .monospaced))
                            .foregroundColor(.secondary)
                    }
                }
                .padding(12)
                .liquidGlass(cornerRadius: 14, showShadow: false)
            }
        }
        .padding(.top, 6)
    }

    private func epicenterMapSection(_ coord: CLLocationCoordinate2D) -> some View {
        EpicenterMapView(coordinate: coord, title: event.place, magnitude: event.magnitude, isPreliminary: event.isPreliminary, rings: FeltArea.perimeter(for: event))
            .frame(height: 220)
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay {
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .strokeBorder(Color.white.opacity(0.18), lineWidth: 0.8)
            }
            .padding(.vertical, 4)
    }

    private var perimeterCard: some View {
        let rings = FeltArea.perimeter(for: event)
        return VStack(alignment: .leading, spacing: 12) {
            Label("Perímetro de sacudida", systemImage: "circle.dotted.circle")
                .font(.headline)
            if event.magnitude == nil {
                Text("Sin magnitud todavía no se puede estimar dónde se sintió.")
            } else if event.coordinate == nil {
                Text("Sin epicentro todavía no se puede estimar dónde se sintió.")
            } else if rings.isEmpty {
                Text("Por su magnitud y profundidad no se espera que se haya sentido en superficie.")
            }
            ForEach(rings) { ring in
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Circle().fill(Color(uiColor: FeltArea.color(ring.intensity)))
                        .frame(width: 12, height: 12)
                    Text("\(FeltArea.roman(ring.intensity)) · \(ring.label)")
                    Spacer(minLength: 4)
                    Text("Hasta \(String(format: "%.0f", ring.radiusKm)) km")
                        .fontWeight(.semibold)
                }
                .font(.subheadline)
            }
            if let local = FeltArea.localIntensity(for: event, at: locationManager.currentCoordinate),
               let location = locationManager.currentCoordinate, let epicenter = event.coordinate {
                Divider()
                let distance = String(format: "%.0f", FeltArea.distanceKm(from: epicenter, to: location))
                Text(local >= FeltArea.felt
                     ? "Donde estás (a \(distance) km): intensidad \(FeltArea.roman(local)), movimiento \(FeltArea.name(local))."
                     : "Donde estás (a \(distance) km) no se espera que se haya sentido.")
                    .font(.subheadline.weight(.semibold))
            } else {
                Text("Permite la ubicación para ver la intensidad estimada donde estás.")
                    .font(.caption).foregroundColor(.secondary)
            }
            Text("Con sacudida fuerte la alarma suena siempre, sin importar tu configuración.")
                .font(.subheadline)
            Text(FeltArea.sourceNote).font(.caption).foregroundColor(.secondary)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .liquidGlass(cornerRadius: 20)
    }

    private var actionButtonsSection: some View {
        VStack(spacing: 12) {
            // 1. Abrir epicentro en mapas
            Button {
                HapticManager.light()
                if let coord = event.coordinate {
                    openEpicenter(coord)
                }
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "map")
                        .font(.system(size: 15, weight: .medium))
                    Text(mapButtonTitle)
                        .font(.system(size: 14.5, weight: .medium))
                }
                .foregroundColor(.primary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .liquidGlass(cornerRadius: 22)
            }
            .buttonStyle(.plain)

            // 2. Abrir fuente oficial (si disponible o entidad)
            if let targetUrl = resolveOfficialURL() {
                Button {
                    HapticManager.light()
                    browserDestination = BrowserDestination(url: targetUrl)
                } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "arrow.up.right.square")
                            .font(.system(size: 15, weight: .medium))
                        Text("Abrir fuente oficial · \(event.agencyDisplayName)")
                            .font(.system(size: 14.5, weight: .medium))
                            .lineLimit(1)
                    }
                    .foregroundColor(.primary)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 14)
                    .liquidGlass(cornerRadius: 22)
                }
                .buttonStyle(.plain)
            }

            // 3. Informar si lo sentí
            Button {
                HapticManager.medium()
                showFeltReport = true
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "text.bubble.fill")
                        .font(.system(size: 15, weight: .medium))
                    Text("Informar si lo sentí")
                        .font(.system(size: 14.5, weight: .medium))
                }
                .foregroundColor(.primary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .liquidGlass(cornerRadius: 22)
            }
            .buttonStyle(.plain)

            // 4. Reportar daños
            Button {
                HapticManager.warning()
                showDamageReport = true
            } label: {
                HStack(spacing: 10) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 15, weight: .bold))
                    Text("Reportar daños")
                        .font(.system(size: 14.5, weight: .bold))
                }
                .foregroundColor(.white)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 14)
                .background(SeismikColors.crimson)
                .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
                .shadow(color: SeismikColors.crimson.opacity(0.35), radius: 8, y: 3)
            }
            .buttonStyle(.plain)
        }
        .padding(.top, 4)
    }

    private var safetySection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("DURANTE UN SISMO")
                .font(.system(size: 11, weight: .bold))
                .tracking(1.4)
                .foregroundColor(.secondary)
                .padding(.top, 8)

            HStack(spacing: 10) {
                SafetyStepCard(number: "1", title: "Agáchate", subtitle: "Antes de caer")
                SafetyStepCard(number: "2", title: "Cúbrete", subtitle: "Bajo una mesa")
                SafetyStepCard(number: "3", title: "Sujétate", subtitle: "Hasta que pare")
            }
        }
    }

    // MARK: - Helpers

    private var mapButtonTitle: String {
        switch MapProviderChoice.stored(mapProvider) {
        case .google: return "Abrir epicentro en Google Maps"
        case .apple: return "Abrir epicentro en Apple Maps"
        }
    }

    private func resolveOfficialURL() -> URL? {
        if let raw = event.officialUrl, let url = URL(string: raw) {
            return url
        }
        // `agency` es opcional: un candidato preliminar todavía no tiene
        // entidad emisora, y entonces no hay página oficial que abrir.
        switch event.agency?.uppercased() {
        case "USGS":
            return URL(string: "https://earthquake.usgs.gov/earthquakes/eventpage/\(event.id)")
        case "SGC":
            return URL(string: "https://www.sgc.gov.co")
        case "EMSC":
            return URL(string: "https://www.emsc-csem.org")
        default:
            return nil
        }
    }

    private func openEpicenter(_ coordinate: CLLocationCoordinate2D) {
        let lat = coordinate.latitude
        let lon = coordinate.longitude
        let query = "\(lat),\(lon)"
        let encodedPlace = (event.place ?? "Epicentro").addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? "Epicentro"

        switch MapProviderChoice.stored(mapProvider) {
        case .google:
            if let appURL = URL(string: "comgooglemaps://?q=\(query)&center=\(query)&zoom=12"),
               UIApplication.shared.canOpenURL(appURL) {
                UIApplication.shared.open(appURL)
                return
            }
            if let webURL = URL(string: "https://www.google.com/maps/search/?api=1&query=\(query)") {
                UIApplication.shared.open(webURL)
            }
        case .apple:
            let placemark = MKPlacemark(coordinate: coordinate)
            let item = MKMapItem(placemark: placemark)
            item.name = "Epicentro: \(event.place ?? "Sismo")"
            if !item.openInMaps() {
                if let webURL = URL(string: "https://maps.apple.com/?ll=\(query)&q=\(encodedPlace)") {
                    UIApplication.shared.open(webURL)
                }
            }
        }
    }
}

// MARK: - Tarjeta de Métrica Detallada (Fiel a screenshots)
private struct DetailedMetricCard: View {
    let icon: String
    let value: String
    let label: String

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Image(systemName: icon)
                .font(.system(size: 15))
                .foregroundColor(.secondary)
                .padding(.bottom, 2)

            Text(value)
                .font(.system(size: 15, weight: .bold))
                .foregroundColor(.primary)
                .fixedSize(horizontal: false, vertical: true)

            Text(label)
                .font(.system(size: 12))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - Tarjeta de Paso de Seguridad
private struct SafetyStepCard: View {
    let number: String
    let title: String
    let subtitle: String

    var body: some View {
        VStack(spacing: 4) {
            Text(number)
                .font(.system(size: 18, weight: .black, design: .rounded))
                .foregroundColor(SeismikColors.glacier)
            Text(title)
                .font(.system(size: 13, weight: .bold))
                .foregroundColor(.primary)
            Text(subtitle)
                .font(.system(size: 10))
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 12)
        .padding(.horizontal, 4)
        .liquidGlass(cornerRadius: 16)
    }
}

// MARK: - Mini Mapa del Epicentro Compatible con Marcador Personalizado
private struct EpicenterMapView: UIViewRepresentable {
    let coordinate: CLLocationCoordinate2D
    let title: String?
    let magnitude: Double?
    let isPreliminary: Bool
    let rings: [FeltArea.Ring]

    func makeUIView(context: Context) -> MKMapView {
        let map = MKMapView()
        map.isScrollEnabled = false
        map.isZoomEnabled = false
        map.delegate = context.coordinator
        let region = MKCoordinateRegion(
            center: coordinate,
            span: MKCoordinateSpan(latitudeDelta: 1.2, longitudeDelta: 1.2)
        )
        map.setRegion(region, animated: false)
        let pin = MKPointAnnotation()
        pin.coordinate = coordinate
        pin.title = title
        map.addAnnotation(pin)
        for ring in rings { map.addOverlay(FeltArea.circle(ring, center: coordinate)) }
        if let outer = rings.first {
            let circle = FeltArea.circle(outer, center: coordinate)
            map.setVisibleMapRect(circle.boundingMapRect,
                                  edgePadding: UIEdgeInsets(top: 28, left: 28, bottom: 28, right: 28),
                                  animated: false)
        }
        return map
    }

    func updateUIView(_ uiView: MKMapView, context: Context) {}

    func makeCoordinator() -> Coordinator {
        Coordinator(magnitude: magnitude, isPreliminary: isPreliminary)
    }

    class Coordinator: NSObject, MKMapViewDelegate {
        let magnitude: Double?
        let isPreliminary: Bool

        init(magnitude: Double?, isPreliminary: Bool) {
            self.magnitude = magnitude
            self.isPreliminary = isPreliminary
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            guard let circle = overlay as? MKCircle else { return MKOverlayRenderer(overlay: overlay) }
            return FeltArea.renderer(for: circle)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            guard !annotation.isKind(of: MKUserLocation.self) else { return nil }
            let identifier = "EpicenterPin"
            var view = mapView.dequeueReusableAnnotationView(withIdentifier: identifier) as? MKMarkerAnnotationView
            if view == nil {
                view = MKMarkerAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                view?.canShowCallout = true
            } else {
                view?.annotation = annotation
            }
            if isPreliminary {
                view?.markerTintColor = SeismikColors.severityUIColor(for: nil, isPreliminary: true)
                view?.glyphImage = UIImage(systemName: "waveform.path")
            } else {
                view?.markerTintColor = SeismikColors.severityUIColor(for: magnitude, isPreliminary: false)
                view?.glyphImage = UIImage(systemName: "exclamationmark")
            }
            return view
        }
    }
}
