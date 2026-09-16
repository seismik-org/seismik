import SwiftUI
import MapKit

/// Comandos imperativos de cámara para mapas MapKit.
public enum MapCameraCommand: Equatable {
    case none
    case centerUser(UUID)
    case centerEarthquakes(UUID)

    var id: UUID? {
        switch self {
        case .none: return nil
        case .centerUser(let id): return id
        case .centerEarthquakes(let id): return id
        }
    }
}

/// Vista principal de monitoreo con Apple MapKit interactivo a pantalla completa y hoja de sismos nativa.
public struct MonitorView: View {
    @StateObject private var state = SeismikState.shared
    @StateObject private var locationManager = LocationManager.shared

    @State private var cameraCommand: MapCameraCommand = .none
    @State private var showSettings = false
    @State private var showEventList = false

    /// Alto que ocupa la barra del historial; el mapa no centra nada debajo.
    private static let historyBarInset: CGFloat = 92

    public init() {}

    public var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .top) {
                // Mapa nativo de Apple MapKit interactivo a pantalla completa
                NativeMapView(
                    state: state,
                    cameraCommand: cameraCommand,
                    coveredBottomInset: Self.historyBarInset
                ) { selectedEvent in
                    state.selectEvent(selectedEvent)
                }
                .ignoresSafeArea()

                FloatingHeaderView(state: state, showSettings: $showSettings)
                    .padding(.top, max(8, geometry.safeAreaInsets.top + 4))

                VStack(alignment: .trailing, spacing: 12) {
                    mapControls
                    // Una barra fija en lugar del panel arrastrable: se toca y la
                    // lista abre en la hoja nativa de iOS. Una hoja siempre visible
                    // taparía la barra de pestañas.
                    HistoryBarView(state: state) {
                        HapticManager.selection()
                        showEventList = true
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 12)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottom)
            }
        }
        // Hoja de Detalle de Sismo Seleccionado en el mapa
        .sheet(item: $state.selectedEvent) { event in
            EventDetailView(event: event)
        }
        // Modal de Configuración
        .sheet(isPresented: $showSettings) {
            SettingsView(state: state)
        }
        // Lista de sismos en la hoja nativa (media y completa)
        .sheet(isPresented: $showEventList) {
            SeismicSheetView(state: state, locationManager: locationManager)
                .modalSheetPresentation()
        }
    }

    /// Botones flotantes de control de mapa.
    private var mapControls: some View {
                VStack(spacing: 12) {
                    Button {
                        HapticManager.light()
                        withAnimation(.easeInOut(duration: 0.2)) {
                            state.cycleMapType()
                        }
                    } label: {
                        Image(systemName: state.appMapType == "satellite" ? "globe.americas" : (state.appMapType == "hybrid" ? "square.3.layers.3d" : "map.fill"))
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(SeismikColors.systemBlue)
                            .frame(width: 44, height: 44)
                            .liquidGlass(cornerRadius: 22)
                    }
                    .buttonStyle(.plain)
                    .contentShape(Circle())
                    .accessibilityLabel("Cambiar estilo del mapa")

                    Button {
                        HapticManager.light()
                        cameraCommand = .centerEarthquakes(UUID())
                    } label: {
                        Image(systemName: "dot.scope")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(SeismikColors.systemBlue)
                            .frame(width: 44, height: 44)
                            .liquidGlass(cornerRadius: 22)
                    }
                    .buttonStyle(.plain)
                    .contentShape(Circle())
                    .accessibilityLabel("Centrar en sismos recientes")

                    Button {
                        HapticManager.light()
                        cameraCommand = .centerUser(UUID())
                    } label: {
                        Image(systemName: "location.fill")
                            .font(.system(size: 16, weight: .semibold))
                            .foregroundColor(SeismikColors.systemBlue)
                            .frame(width: 44, height: 44)
                            .liquidGlass(cornerRadius: 22)
                    }
                    .buttonStyle(.plain)
                    .contentShape(Circle())
                    .accessibilityLabel("Centrar mapa en mi ubicación")
                }
    }
}

// MARK: - Mapa Nativo de Apple Compatible (iOS 15 - iOS 18+)
private struct NativeMapView: UIViewRepresentable {
    @ObservedObject var state: SeismikState
    let cameraCommand: MapCameraCommand
    let coveredBottomInset: CGFloat
    let onSelectEvent: (SeismicEvent) -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> MKMapView {
        let mapView = MKMapView()
        mapView.delegate = context.coordinator
        mapView.showsUserLocation = true
        mapView.showsCompass = true
        mapView.showsScale = true
        mapView.pointOfInterestFilter = .excludingAll

        let defaultRegion = MKCoordinateRegion(
            center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
            span: MKCoordinateSpan(latitudeDelta: 12.0, longitudeDelta: 12.0)
        )
        mapView.setRegion(defaultRegion, animated: false)

        return mapView
    }

    func updateUIView(_ mapView: MKMapView, context: Context) {
        let targetType: MKMapType
        switch state.appMapType {
        case "satellite": targetType = .satellite
        case "hybrid": targetType = .hybrid
        default: targetType = .standard
        }
        if mapView.mapType != targetType {
            mapView.mapType = targetType
        }

        mapView.layoutMargins = UIEdgeInsets(
            top: 96,
            left: 12,
            bottom: max(coveredBottomInset + 10, 148),
            right: 12
        )

        if let cmdId = cameraCommand.id, cmdId != context.coordinator.lastCommandId {
            context.coordinator.lastCommandId = cmdId
            switch cameraCommand {
            case .none:
                break
            case .centerUser:
                let userCoord = mapView.userLocation.location?.coordinate ?? LocationManager.shared.currentCoordinate
                if let coord = userCoord {
                    let region = MKCoordinateRegion(
                        center: coord,
                        span: MKCoordinateSpan(latitudeDelta: 0.8, longitudeDelta: 0.8)
                    )
                    mapView.setRegion(region, animated: true)
                    mapView.setUserTrackingMode(.follow, animated: true)
                } else {
                    LocationManager.shared.requestPermission()
                    LocationManager.shared.startUpdating()
                    mapView.setUserTrackingMode(.follow, animated: true)
                }
            case .centerEarthquakes:
                mapView.setUserTrackingMode(.none, animated: false)
                if let latest = state.events.first, let coord = latest.coordinate {
                    let region = MKCoordinateRegion(
                        center: coord,
                        span: MKCoordinateSpan(latitudeDelta: 2.2, longitudeDelta: 2.2)
                    )
                    mapView.setRegion(region, animated: true)
                } else {
                    let defaultRegion = MKCoordinateRegion(
                        center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
                        span: MKCoordinateSpan(latitudeDelta: 6.5, longitudeDelta: 6.5)
                    )
                    mapView.setRegion(defaultRegion, animated: true)
                }
            }
        }

        context.coordinator.syncAnnotations(mapView: mapView, events: state.events, stations: state.stations)
    }

    class Coordinator: NSObject, MKMapViewDelegate {
        var parent: NativeMapView
        var lastCommandId: UUID?
        private var lastEventSnapshots: [String] = []
        private var lastStationSnapshots: [String] = []
        private var lastWaveSnapshots: [String] = []

        init(_ parent: NativeMapView) {
            self.parent = parent
        }

        func syncAnnotations(mapView: MKMapView, events: [SeismicEvent], stations: [SeismicStation]) {
            syncPerimeters(mapView: mapView, events: events)
            let eventSnapshots = events.map {
                "\($0.id)|\($0.magnitude ?? -1)|\($0.latitude ?? 999)|\($0.longitude ?? 999)|\($0.isPreliminary)"
            }
            let stationSnapshots = stations.map {
                "\($0.id)|\($0.latitude)|\($0.longitude)"
            }

            guard eventSnapshots != lastEventSnapshots || stationSnapshots != lastStationSnapshots else { return }
            lastEventSnapshots = eventSnapshots
            lastStationSnapshots = stationSnapshots

            let current = mapView.annotations.filter { !($0 is MKUserLocation) }
            mapView.removeAnnotations(current)

            var newAnnotations: [MKAnnotation] = []

            for event in events {
                if let coord = event.coordinate {
                    newAnnotations.append(SeismicPointAnnotation(event: event, coordinate: coord))
                }
            }

            for station in stations {
                newAnnotations.append(StationPointAnnotation(station: station))
            }

            mapView.addAnnotations(newAnnotations)
        }

        /// Alcance estimado III/VI de eventos oficiales y preliminares recientes.
        private func syncPerimeters(mapView: MKMapView, events: [SeismicEvent]) {
            let recent = FeltArea.recentEvents(events)
            let snapshots = recent.map { "\($0.id)|\($0.latitude ?? 0)|\($0.longitude ?? 0)|\($0.magnitude ?? 0)|\($0.depthKm ?? 10)" }
            guard snapshots != lastWaveSnapshots else { return }
            lastWaveSnapshots = snapshots
            mapView.removeOverlays(mapView.overlays.filter { $0 is MKCircle })
            for event in recent {
                guard let coordinate = event.coordinate else { continue }
                for ring in FeltArea.perimeter(for: event) where ring.intensity == 3 || ring.intensity == 6 {
                    mapView.addOverlay(FeltArea.circle(ring, center: coordinate))
                }
            }
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let circle = overlay as? MKCircle {
                return FeltArea.renderer(for: circle)
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func mapView(_ mapView: MKMapView, viewFor annotation: MKAnnotation) -> MKAnnotationView? {
            if annotation is MKUserLocation {
                return nil // Punto de ubicación nativo de Apple
            }

            if let seismic = annotation as? SeismicPointAnnotation {
                let identifier = "SeismicBadgeAnnotation"
                let annotationView = mapView.dequeueReusableAnnotationView(
                    withIdentifier: identifier
                ) as? MagnitudeAnnotationView
                    ?? MagnitudeAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                annotationView.annotation = annotation
                annotationView.configure(with: seismic.event)
                annotationView.clusteringIdentifier = "seismik-events"
                return annotationView
            }

            if let cluster = annotation as? MKClusterAnnotation {
                let identifier = "SeismicClusterAnnotation"
                let marker = mapView.dequeueReusableAnnotationView(
                    withIdentifier: identifier
                ) as? MKMarkerAnnotationView
                    ?? MKMarkerAnnotationView(annotation: cluster, reuseIdentifier: identifier)
                marker.annotation = cluster
                marker.markerTintColor = UIColor.systemIndigo
                marker.glyphText = "\(cluster.memberAnnotations.count)"
                marker.titleVisibility = .hidden
                marker.subtitleVisibility = .hidden
                marker.displayPriority = .defaultHigh
                marker.accessibilityLabel = "\(cluster.memberAnnotations.count) sismos agrupados"
                return marker
            }

            if annotation is StationPointAnnotation {
                let identifier = "StationDotAnnotation"
                var annotationView = mapView.dequeueReusableAnnotationView(withIdentifier: identifier)
                if annotationView == nil {
                    annotationView = MKAnnotationView(annotation: annotation, reuseIdentifier: identifier)
                    annotationView?.canShowCallout = true
                    let dot = UIView(frame: CGRect(x: 0, y: 0, width: 8, height: 8))
                    dot.backgroundColor = UIColor(red: 0.22, green: 0.74, blue: 0.96, alpha: 0.85)
                    dot.layer.cornerRadius = 4
                    dot.layer.borderWidth = 1.2
                    dot.layer.borderColor = UIColor.white.cgColor
                    annotationView?.addSubview(dot)
                    annotationView?.frame = CGRect(x: 0, y: 0, width: 8, height: 8)
                } else {
                    annotationView?.annotation = annotation
                }
                return annotationView
            }

            return nil
        }

        func mapView(_ mapView: MKMapView, didSelect view: MKAnnotationView) {
            if let seismic = view.annotation as? SeismicPointAnnotation {
                HapticManager.light()
                parent.onSelectEvent(seismic.event)
            }
        }
    }
}



private final class MagnitudeAnnotationView: MKAnnotationView {
    private let magnitudeLabel = UILabel()

    override init(annotation: MKAnnotation?, reuseIdentifier: String?) {
        super.init(annotation: annotation, reuseIdentifier: reuseIdentifier)
        bounds = CGRect(x: 0, y: 0, width: 48, height: 32)
        centerOffset = CGPoint(x: 0, y: -18)
        canShowCallout = false
        collisionMode = .rectangle
        displayPriority = .required
        layer.cornerRadius = 12
        layer.cornerCurve = .continuous
        layer.borderWidth = 1
        layer.borderColor = UIColor.white.withAlphaComponent(0.8).cgColor
        layer.shadowColor = UIColor.black.cgColor
        layer.shadowOpacity = 0.22
        layer.shadowRadius = 4
        layer.shadowOffset = CGSize(width: 0, height: 2)

        magnitudeLabel.translatesAutoresizingMaskIntoConstraints = false
        magnitudeLabel.textAlignment = .center
        magnitudeLabel.textColor = .white
        magnitudeLabel.font = .rounded(ofSize: 14, weight: .bold)
        magnitudeLabel.adjustsFontSizeToFitWidth = true
        magnitudeLabel.minimumScaleFactor = 0.8
        addSubview(magnitudeLabel)
        NSLayoutConstraint.activate([
            magnitudeLabel.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 4),
            magnitudeLabel.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -4),
            magnitudeLabel.topAnchor.constraint(equalTo: topAnchor),
            magnitudeLabel.bottomAnchor.constraint(equalTo: bottomAnchor)
        ])
        isAccessibilityElement = true
        accessibilityTraits = .button
    }

    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    func configure(with event: SeismicEvent) {
        if event.isPreliminary && event.magnitude == nil {
            magnitudeLabel.text = "P"
            backgroundColor = SeismikColors.severityUIColor(for: nil, isPreliminary: true)
            accessibilityLabel = "Sismo preliminar, magnitud pendiente"
            return
        }
        let magnitude = event.magnitude
        magnitudeLabel.text = magnitude.map { String(format: "%.1f", $0) } ?? "—"
        backgroundColor = SeismikColors.severityUIColor(for: magnitude, isPreliminary: event.isPreliminary)
        accessibilityLabel = magnitude.map { "Sismo de magnitud \(String(format: "%.1f", $0))" }
            ?? "Sismo con magnitud pendiente"
        accessibilityHint = "Abre el detalle del sismo"
    }

    override func setSelected(_ selected: Bool, animated: Bool) {
        super.setSelected(selected, animated: animated)
        let changes = {
            self.transform = selected ? CGAffineTransform(scaleX: 1.18, y: 1.18) : .identity
            self.layer.borderWidth = selected ? 2.5 : 1
        }
        if animated {
            UIView.animate(withDuration: 0.18, animations: changes)
        } else {
            changes()
        }
        accessibilityTraits = selected ? [.button, .selected] : .button
    }

    override func prepareForReuse() {
        super.prepareForReuse()
        transform = .identity
        layer.borderWidth = 1
    }
}

private extension UIFont {
    static func rounded(ofSize size: CGFloat, weight: UIFont.Weight) -> UIFont {
        let base = UIFont.systemFont(ofSize: size, weight: weight)
        guard let descriptor = base.fontDescriptor.withDesign(.rounded) else { return base }
        return UIFont(descriptor: descriptor, size: size)
    }
}

// MARK: - Modelos de Anotación MapKit
private class SeismicPointAnnotation: NSObject, MKAnnotation {
    let event: SeismicEvent
    dynamic var coordinate: CLLocationCoordinate2D

    init(event: SeismicEvent, coordinate: CLLocationCoordinate2D) {
        self.event = event
        self.coordinate = coordinate
        super.init()
    }

    var title: String? { event.place ?? "Sismo" }
}

private class StationPointAnnotation: NSObject, MKAnnotation {
    let station: SeismicStation
    dynamic var coordinate: CLLocationCoordinate2D

    init(station: SeismicStation) {
        self.station = station
        self.coordinate = station.coordinate
        super.init()
    }

    var title: String? { "Estación \(station.id)" }
}
