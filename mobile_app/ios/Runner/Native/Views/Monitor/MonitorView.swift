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
    @State private var showFeltReport = false
    @State private var showDamageReport = false
    @State private var drawerPosition: DrawerPosition = .peek
    @State private var drawerTranslation: CGFloat = 0
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    public init() {}

    public var body: some View {
        GeometryReader { geometry in
            let expandedHeight = max(geometry.size.height - geometry.safeAreaInsets.top - 12, 420)
            let visibleHeight = drawerPosition.height(in: geometry.size.height)
            let baseOffset = expandedHeight - visibleHeight
            let drawerOffset = min(
                max(baseOffset + drawerTranslation, 0),
                expandedHeight - DrawerPosition.peek.height(in: geometry.size.height)
            )

            ZStack(alignment: .top) {
                // Mapa nativo de Apple MapKit interactivo a pantalla completa
                NativeMapView(
                    state: state,
                    cameraCommand: cameraCommand,
                    coveredBottomInset: visibleHeight
                ) { selectedEvent in
                    state.selectEvent(selectedEvent)
                }
                .ignoresSafeArea()

                FloatingHeaderView(state: state, showSettings: $showSettings)
                    .padding(.top, max(8, geometry.safeAreaInsets.top + 4))

                // Hoja inferior interactiva de sismos (Drawer)
                SeismicSheetView(
                    state: state,
                    locationManager: locationManager,
                    showFeltReport: $showFeltReport,
                    showDamageReport: $showDamageReport,
                    onDrawerDragChanged: { drawerTranslation = $0 },
                    onDrawerDragEnded: { dragDistance, projectedDistance in
                        settleDrawer(
                            dragDistance: dragDistance,
                            projectedDistance: projectedDistance,
                            expandedHeight: expandedHeight,
                            screenHeight: geometry.size.height
                        )
                    },
                    onDrawerHandleTapped: cycleDrawer
                )
                .frame(height: expandedHeight)
                .offset(y: drawerOffset)
                .frame(maxHeight: .infinity, alignment: .bottom)

                // Botones flotantes de control de mapa (en primer plano)
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
                    .accessibilityLabel("Centrar mapa en mi ubicación")
                }
                .padding(.trailing, 18)
                .padding(.bottom, DrawerPosition.peek.height(in: geometry.size.height) + 16)
                .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .bottomTrailing)
                .zIndex(10)
                .opacity(max(0.0, min(1.0, 1.0 - (visibleHeight - DrawerPosition.peek.height(in: geometry.size.height)) / 60.0)))
                .allowsHitTesting(visibleHeight <= DrawerPosition.peek.height(in: geometry.size.height) + 15)
            }
        }
        // Hoja de Detalle de Sismo Seleccionado
        .sheet(item: $state.selectedEvent) { event in
            EventDetailView(event: event)
        }
        // Modal de Configuración
        .sheet(isPresented: $showSettings) {
            SettingsView(state: state)
        }
        // Modal de Reporte "¿Lo sentiste?"
        .sheet(isPresented: $showFeltReport) {
            FeltReportView(preselectedEvent: state.events.first)
        }
        // Modal de Reporte de Daños
        .sheet(isPresented: $showDamageReport) {
            DamageReportView(preselectedEvent: state.events.first)
        }
        // Superposición de Alerta de Emergencia Crítica
        .overlay {
            if let alertEvent = state.activeAlert {
                EmergencyAlertView(event: alertEvent) {
                    state.dismissAlert()
                }
                .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
        }
    }

    private func settleDrawer(
        dragDistance: CGFloat,
        projectedDistance: CGFloat,
        expandedHeight: CGFloat,
        screenHeight: CGFloat
    ) {
        let peekH = DrawerPosition.peek.height(in: screenHeight)
        let medH = DrawerPosition.medium.height(in: screenHeight)
        let expH = DrawerPosition.expanded.height(in: screenHeight)

        let currentH = drawerPosition.height(in: screenHeight) - dragDistance
        let velocity = projectedDistance - dragDistance
        // Proyección continua con inercia según la velocidad del arrastre
        let targetH = currentH - (velocity * 0.45)

        let detents: [(DrawerPosition, CGFloat)] = [
            (.peek, peekH),
            (.medium, medH),
            (.expanded, expH)
        ]

        let best = detents.min(by: { abs($0.1 - targetH) < abs($1.1 - targetH) })?.0 ?? .peek

        withAnimation(drawerAnimation) {
            drawerTranslation = 0
            drawerPosition = best
        }
        HapticManager.selection()
    }

    private func cycleDrawer() {
        withAnimation(drawerAnimation) {
            switch drawerPosition {
            case .peek: drawerPosition = .medium
            case .medium: drawerPosition = .expanded
            case .expanded: drawerPosition = .peek
            }
        }
        HapticManager.selection()
    }

    private var drawerAnimation: Animation {
        reduceMotion ? .easeOut(duration: 0.20) : .interactiveSpring(response: 0.32, dampingFraction: 0.82)
    }
}

private enum DrawerPosition: CaseIterable {
    case peek
    case medium
    case expanded

    func height(in screenHeight: CGFloat) -> CGFloat {
        switch self {
        case .peek: return 185
        case .medium: return max(350, screenHeight * 0.46)
        case .expanded: return max(450, screenHeight * 0.86)
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
                if mapView.userLocation.location != nil {
                    let coord = mapView.userLocation.coordinate
                    mapView.setRegion(
                        MKCoordinateRegion(center: coord, span: MKCoordinateSpan(latitudeDelta: 2.0, longitudeDelta: 2.0)),
                        animated: true
                    )
                } else if let coord = LocationManager.shared.currentCoordinate {
                    mapView.setRegion(
                        MKCoordinateRegion(center: coord, span: MKCoordinateSpan(latitudeDelta: 2.0, longitudeDelta: 2.0)),
                        animated: true
                    )
                } else {
                    LocationManager.shared.requestPermission()
                    LocationManager.shared.startUpdating()
                }
            case .centerEarthquakes:
                let seismicAnnotations = mapView.annotations.filter { $0 is SeismicPointAnnotation }
                if !seismicAnnotations.isEmpty {
                    mapView.showAnnotations(seismicAnnotations, animated: true)
                } else {
                    let defaultRegion = MKCoordinateRegion(
                        center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
                        span: MKCoordinateSpan(latitudeDelta: 9.0, longitudeDelta: 9.0)
                    )
                    mapView.setRegion(defaultRegion, animated: true)
                }
            }
        }

        context.coordinator.syncOverlays(mapView: mapView, provider: state.mapProvider)
        context.coordinator.syncAnnotations(mapView: mapView, events: state.events, stations: state.stations)
    }

    class Coordinator: NSObject, MKMapViewDelegate {
        var parent: NativeMapView
        var lastCommandId: UUID?
        private var lastEventSnapshots: [String] = []
        private var lastStationSnapshots: [String] = []

        init(_ parent: NativeMapView) {
            self.parent = parent
        }

        func syncOverlays(mapView: MKMapView, provider: String) {
            let hasOsm = mapView.overlays.contains { $0 is MKTileOverlay }
            if provider == "osm" {
                if !hasOsm {
                    let osm = MKTileOverlay(urlTemplate: "https://tile.openstreetmap.org/{z}/{x}/{y}.png")
                    osm.canReplaceMapContent = true
                    mapView.addOverlay(osm, level: .aboveLabels)
                }
            } else {
                if hasOsm {
                    let osmOverlays = mapView.overlays.filter { $0 is MKTileOverlay }
                    mapView.removeOverlays(osmOverlays)
                }
            }
        }

        func mapView(_ mapView: MKMapView, rendererFor overlay: MKOverlay) -> MKOverlayRenderer {
            if let tile = overlay as? MKTileOverlay {
                return MKTileOverlayRenderer(tileOverlay: tile)
            }
            return MKOverlayRenderer(overlay: overlay)
        }

        func syncAnnotations(mapView: MKMapView, events: [SeismicEvent], stations: [SeismicStation]) {
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
