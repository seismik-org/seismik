import SwiftUI
import MapKit
import GoogleMaps

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
    /// Se lee aquí, y no en `state`, para que el mapa cambie en cuanto se
    /// elija otro proveedor en Configuración.
    @AppStorage("seismik.map_provider") private var mapProviderSetting = MapProviderChoice.apple.rawValue

    /// Alto que ocupa la barra del historial; el mapa no centra nada debajo.
    private static let historyBarInset: CGFloat = 92

    public init() {}

    public var body: some View {
        GeometryReader { geometry in
            ZStack(alignment: .top) {
                // Mapa interactivo a pantalla completa, del proveedor elegido.
                Group {
                    if mapProvider == .google {
                        GoogleMonitorMapView(
                            state: state,
                            cameraCommand: cameraCommand,
                            coveredBottomInset: Self.historyBarInset
                        ) { selectedEvent in
                            state.selectEvent(selectedEvent)
                        }
                    } else {
                        NativeMapView(
                            state: state,
                            cameraCommand: cameraCommand,
                            coveredBottomInset: Self.historyBarInset
                        ) { selectedEvent in
                            state.selectEvent(selectedEvent)
                        }
                    }
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

    /// Proveedor que se puede dibujar de verdad en este build.
    private var mapProvider: MapProviderChoice {
        MapProviderChoice.resolved(stored: mapProviderSetting, googleIsReady: GoogleMapsBridge.isAvailable)
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

// MARK: - Mapa de Google a pantalla completa
/// Misma información que `NativeMapView` —sismos, estaciones y perímetro de
/// sacudida— sobre los mosaicos de Google. Google Maps no agrupa marcadores sin
/// la librería de utilidades, así que aquí cada sismo se dibuja por separado.
private struct GoogleMonitorMapView: UIViewRepresentable {
    @ObservedObject var state: SeismikState
    let cameraCommand: MapCameraCommand
    let coveredBottomInset: CGFloat
    let onSelectEvent: (SeismicEvent) -> Void

    /// Equivalencias con los tramos que usa el mapa de Apple: 0.8° de alto son
    /// unos 8.5 de zoom, y 2.2° unos 7.
    private static let userZoom: Float = 8.5
    private static let eventsZoom: Float = 7.0
    private static let countryZoom: Float = 5.4

    func makeCoordinator() -> Coordinator {
        Coordinator(self)
    }

    func makeUIView(context: Context) -> GMSMapView {
        let camera = GMSCameraPosition.camera(
            withLatitude: 4.65,
            longitude: -74.05,
            zoom: Self.countryZoom
        )
        let mapView = GMSMapView(frame: .zero, camera: camera)
        mapView.delegate = context.coordinator
        mapView.isMyLocationEnabled = true
        mapView.settings.compassButton = true
        mapView.settings.myLocationButton = false
        mapView.settings.rotateGestures = false
        mapView.settings.tiltGestures = false
        return mapView
    }

    func updateUIView(_ mapView: GMSMapView, context: Context) {
        switch state.appMapType {
        case "satellite": mapView.mapType = .satellite
        case "hybrid": mapView.mapType = .hybrid
        default: mapView.mapType = .normal
        }

        // El logo y la atribución de Google no pueden quedar bajo la barra del
        // historial: la licencia del SDK exige que se vean.
        mapView.padding = UIEdgeInsets(
            top: 96,
            left: 12,
            bottom: max(coveredBottomInset + 10, 148),
            right: 12
        )

        if let commandId = cameraCommand.id, commandId != context.coordinator.lastCommandId {
            context.coordinator.lastCommandId = commandId
            switch cameraCommand {
            case .none:
                break
            case .centerUser:
                let coordinate = mapView.myLocation?.coordinate ?? LocationManager.shared.currentCoordinate
                if let coordinate {
                    mapView.animate(with: GMSCameraUpdate.setTarget(coordinate, zoom: Self.userZoom))
                } else {
                    LocationManager.shared.requestPermission()
                    LocationManager.shared.startUpdating()
                }
            case .centerEarthquakes:
                if let latest = state.events.first, let coordinate = latest.coordinate {
                    mapView.animate(with: GMSCameraUpdate.setTarget(coordinate, zoom: Self.eventsZoom))
                } else {
                    mapView.animate(with: GMSCameraUpdate.setTarget(
                        CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
                        zoom: Self.countryZoom
                    ))
                }
            }
        }

        context.coordinator.sync(mapView: mapView, events: state.events, stations: state.stations)
    }

    class Coordinator: NSObject, GMSMapViewDelegate {
        var parent: GoogleMonitorMapView
        var lastCommandId: UUID?
        private var lastEventSnapshots: [String] = []
        private var lastStationSnapshots: [String] = []
        private var lastPerimeterSnapshots: [String] = []
        private var markers: [GMSMarker] = []
        private var circles: [GMSCircle] = []

        init(_ parent: GoogleMonitorMapView) {
            self.parent = parent
        }

        func sync(mapView: GMSMapView, events: [SeismicEvent], stations: [SeismicStation]) {
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

            for marker in markers { marker.map = nil }
            markers.removeAll(keepingCapacity: true)

            for event in events {
                guard let coordinate = event.coordinate else { continue }
                let marker = GMSMarker(position: coordinate)
                marker.icon = GoogleMarkerIcon.magnitude(for: event)
                marker.groundAnchor = CGPoint(x: 0.5, y: 0.5)
                marker.title = event.place ?? "Sismo"
                marker.userData = event
                marker.zIndex = 2
                marker.map = mapView
                markers.append(marker)
            }

            for station in stations {
                let marker = GMSMarker(position: station.coordinate)
                marker.icon = GoogleMarkerIcon.station
                marker.groundAnchor = CGPoint(x: 0.5, y: 0.5)
                marker.title = "Estación \(station.id)"
                marker.zIndex = 1
                marker.map = mapView
                markers.append(marker)
            }
        }

        /// Alcance estimado III/VI de eventos oficiales y preliminares recientes.
        private func syncPerimeters(mapView: GMSMapView, events: [SeismicEvent]) {
            let recent = FeltArea.recentEvents(events)
            let snapshots = recent.map {
                "\($0.id)|\($0.latitude ?? 0)|\($0.longitude ?? 0)|\($0.magnitude ?? 0)|\($0.depthKm ?? 10)"
            }
            guard snapshots != lastPerimeterSnapshots else { return }
            lastPerimeterSnapshots = snapshots

            for circle in circles { circle.map = nil }
            circles.removeAll(keepingCapacity: true)

            for event in recent {
                guard let coordinate = event.coordinate else { continue }
                for ring in FeltArea.perimeter(for: event) where ring.intensity == 3 || ring.intensity == 6 {
                    let circle = GoogleMarkerIcon.circle(ring, center: coordinate)
                    circle.map = mapView
                    circles.append(circle)
                }
            }
        }

        func mapView(_ mapView: GMSMapView, didTap marker: GMSMarker) -> Bool {
            guard let event = marker.userData as? SeismicEvent else { return false }
            HapticManager.light()
            parent.onSelectEvent(event)
            return true
        }
    }
}

// MARK: - Dibujos para los marcadores de Google
/// Google Maps pinta imágenes, no vistas: la pastilla de magnitud se dibuja una
/// vez por valor y se guarda, porque el mapa se vuelve a sincronizar con cada
/// refresco de la lista.
enum GoogleMarkerIcon {
    private static var badges: [String: UIImage] = [:]

    static func magnitude(for event: SeismicEvent) -> UIImage {
        let text: String
        let color: UIColor
        if event.isPreliminary && event.magnitude == nil {
            text = "P"
            color = SeismikColors.severityUIColor(for: nil, isPreliminary: true)
        } else {
            text = event.magnitude.map { String(format: "%.1f", $0) } ?? "—"
            color = SeismikColors.severityUIColor(for: event.magnitude, isPreliminary: event.isPreliminary)
        }

        // El color sale de la magnitud, así que el texto y el sello preliminar
        // identifican el dibujo por completo.
        let key = "\(text)|\(event.isPreliminary)"
        if let cached = badges[key] { return cached }

        let size = CGSize(width: 48, height: 32)
        let image = UIGraphicsImageRenderer(size: size).image { _ in
            let rect = CGRect(origin: .zero, size: size).insetBy(dx: 2, dy: 2)
            let shape = UIBezierPath(roundedRect: rect, cornerRadius: 12)
            color.setFill()
            shape.fill()
            UIColor.white.withAlphaComponent(0.8).setStroke()
            shape.lineWidth = 1
            shape.stroke()

            let attributes: [NSAttributedString.Key: Any] = [
                .font: UIFont.roundedForMarkers(ofSize: 14, weight: .bold),
                .foregroundColor: UIColor.white
            ]
            let measured = text.size(withAttributes: attributes)
            text.draw(
                at: CGPoint(x: rect.midX - measured.width / 2, y: rect.midY - measured.height / 2),
                withAttributes: attributes
            )
        }
        badges[key] = image
        return image
    }

    static let station: UIImage = {
        let size = CGSize(width: 12, height: 12)
        return UIGraphicsImageRenderer(size: size).image { _ in
            let rect = CGRect(origin: .zero, size: size).insetBy(dx: 1.4, dy: 1.4)
            let dot = UIBezierPath(ovalIn: rect)
            UIColor(red: 0.22, green: 0.74, blue: 0.96, alpha: 0.85).setFill()
            dot.fill()
            UIColor.white.setStroke()
            dot.lineWidth = 1.2
            dot.stroke()
        }
    }()

    /// Mismo anillo que dibuja `FeltArea` en MapKit, con los colores intactos.
    static func circle(_ ring: FeltArea.Ring, center: CLLocationCoordinate2D) -> GMSCircle {
        let circle = GMSCircle(position: center, radius: ring.radiusKm * 1_000)
        let color = FeltArea.color(ring.intensity)
        circle.strokeColor = color.withAlphaComponent(0.85)
        circle.fillColor = color.withAlphaComponent(ring.intensity == 3 ? 0.08 : 0.14)
        circle.strokeWidth = ring.intensity == 3 ? 2 : 1
        return circle
    }

    /// Encuadre que cubre un radio en kilómetros alrededor de un punto.
    static func bounds(around center: CLLocationCoordinate2D, radiusKm: Double) -> GMSCoordinateBounds {
        let latitudeDelta = radiusKm / 110.574
        let cosine = max(0.01, cos(center.latitude * .pi / 180))
        let longitudeDelta = radiusKm / (111.320 * cosine)
        let northEast = CLLocationCoordinate2D(
            latitude: min(85, center.latitude + latitudeDelta),
            longitude: center.longitude + longitudeDelta
        )
        let southWest = CLLocationCoordinate2D(
            latitude: max(-85, center.latitude - latitudeDelta),
            longitude: center.longitude - longitudeDelta
        )
        return GMSCoordinateBounds(coordinate: northEast, coordinate: southWest)
    }
}

extension UIFont {
    /// Tipografía redondeada de los marcadores dibujados para Google Maps.
    static func roundedForMarkers(ofSize size: CGFloat, weight: UIFont.Weight) -> UIFont {
        let base = UIFont.systemFont(ofSize: size, weight: weight)
        guard let descriptor = base.fontDescriptor.withDesign(.rounded) else { return base }
        return UIFont(descriptor: descriptor, size: size)
    }
}
