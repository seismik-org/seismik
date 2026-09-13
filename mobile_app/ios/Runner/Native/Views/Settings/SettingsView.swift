import AuthenticationServices
import CoreLocation
import MapKit
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
    @State private var browserDestination: BrowserDestination?
    @State private var showSignInProviders = false
    @State private var account: SeismikAccount? = SeismikAPIClient.shared.signedInAccount
    @State private var accountError: String?

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

                            Text("Versión \(versionDescription)")
                                .font(.system(size: 14, weight: .semibold, design: .rounded))
                                .foregroundColor(SeismikColors.systemBlue)

                            Text("Beta experimental")
                                .font(.system(size: 12, weight: .regular))
                                .foregroundColor(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }

                Section(header: Text("Cuenta Seismik")) {
                    if let account {
                        HStack(spacing: 12) {
                            Image(systemName: "person.crop.circle.fill")
                                .foregroundColor(SeismikColors.systemBlue)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(account.name.isEmpty ? "Cuenta Seismik" : account.name)
                                Text(account.email).font(.caption).foregroundColor(.secondary)
                            }
                            Spacer()
                            Button("Salir", role: .destructive) {
                                Task {
                                    await state.signOutAccount()
                                    self.account = nil
                                }
                            }
                        }
                    } else {
                        Button {
                            showSignInProviders = true
                        } label: {
                            Label("Iniciar sesión", systemImage: "person.badge.key")
                        }
                    }
                    Text("La cuenta identifica a tu familia en la pestaña Familia. Nunca comparte tu ubicación sin una acción explícita.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                // Alertas críticas (Pantalla completa, simulacro, magnitudes y radio)
                Section(header: Text("Alertas críticas")) {
                    Button(action: requestNotificationPermission) {
                        HStack {
                            VStack(alignment: .leading, spacing: 3) {
                                Text("Activar alertas")
                                    .font(.body)
                                    .foregroundColor(.primary)
                                Text("Las alertas críticas requieren aprobación de Apple; mientras tanto se usan avisos urgentes normales.")
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
                    .onChange(of: state.receiveEarlyAlerts) { _ in saveAlertPreferences() }

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
                    .onChange(of: state.receiveOfficialUpdates) { _ in saveAlertPreferences() }

                    // Deslizador continuo de magnitud mínima para alerta
                    SliderRow(
                        title: "Magnitud mínima para aviso oficial",
                        value: $state.minimumNotificationMagnitude,
                        range: 2.0...8.0,
                        step: 0.5,
                        format: "%.1f",
                        prefix: "M"
                    ) {
                        saveAlertPreferences()
                    }

                    Text("Las alertas tempranas preliminares usan una zona estimada de sacudida; una magnitud alta puede avisarte aunque esté más lejos si el movimiento podría sentirse. No reemplaza un boletín oficial.")
                        .font(.caption)
                        .foregroundColor(.secondary)

                    // Chips interactivos de radio de cercanía (idénticos a Android)
                    ProximityRadiusChipsView(selectedRadius: $state.alertRadiusKm) {
                        saveAlertPreferences()
                    }
                }

                // Mapas y sincronización
                Section(header: Text("Mapas y sincronización")) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text("Proveedor de mapas")
                            .font(.body)
                        Text("Apple Maps y OpenStreetMap funcionan dentro de la app. Google Maps abre los epicentros en la app oficial de Google Maps.")
                            .font(.caption)
                            .foregroundColor(.secondary)

                        HStack {
                            Text("Proveedor:")
                                .font(.subheadline)
                                .foregroundColor(.secondary)
                            Spacer()
                            Picker("Proveedor de mapas", selection: $state.mapProvider) {
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
                        if state.pendingReportCount > 0 {
                            Button("Reintentar") {
                                Task { await state.flushPendingReports() }
                            }
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(SeismikColors.systemBlue)
                        }
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
                Section(
                    header: Text("Privacidad y sensores"),
                    footer: Text("Los reportes necesitan una ubicación. La detección colaborativa usa el acelerómetro únicamente cuando está activada.")
                ) {
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
                    .onChange(of: state.crowdsourcingEnabled) { _ in
                        state.syncCrowdsourcing()
                    }

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
                            Image(systemName: "shield.lefthalf.fill")
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
                        Label("Registro de alertas", systemImage: state.isRegistered ? "checkmark.shield.fill" : "exclamationmark.shield")
                        Spacer()
                        Text(state.isRegistered ? "Activo" : "Pendiente")
                            .foregroundColor(state.isRegistered ? SeismikColors.emerald : SeismikColors.amber)
                    }

                    HStack {
                        Label("Notificaciones", systemImage: "bell.badge")
                        Spacer()
                        Text(notificationStatusLabel)
                            .foregroundColor(.secondary)
                    }

                    HStack {
                        Label("Ubicación", systemImage: "location.fill")
                        Spacer()
                        Text(locationStatusLabel)
                            .foregroundColor(.secondary)
                    }

                    if let issue = state.registrationIssue, !state.isRegistered {
                        Text(issue)
                            .font(.caption)
                            .foregroundColor(SeismikColors.amber)
                            .fixedSize(horizontal: false, vertical: true)
                    }

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
                Section(
                    header: Text("Acerca de Seismik"),
                    footer: Text("Los cambios quedan guardados en el teléfono y se aplican inmediatamente. Seismik continúa en beta experimental y no sustituye a las autoridades.")
                ) {
                    HStack {
                        Text("Versión")
                        Spacer()
                        Text(versionDescription)
                            .foregroundColor(.secondary)
                            .monospacedDigit()
                    }

                    Button("Sitio web oficial") {
                        browserDestination = BrowserDestination(url: URL(string: "https://seismik.org")!)
                    }

                    Button("Documentación y código abierto") {
                        browserDestination = BrowserDestination(url: URL(string: "https://github.com/seismik-org/seismik")!)
                    }

                    Button("Privacidad") {
                        browserDestination = BrowserDestination(url: URL(string: "https://seismik.org/terms-of-privacy")!)
                    }

                    Button("Términos del servicio") {
                        browserDestination = BrowserDestination(url: URL(string: "https://seismik.org/terms-of-service")!)
                    }
                }
            }
            .navigationTitle("Configuración")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
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
                notificationStatus = await UNUserNotificationCenter.current()
                    .notificationSettings().authorizationStatus
            }
            .sheet(item: $browserDestination) { destination in
                InAppBrowserView(url: destination.url)
                    .ignoresSafeArea()
            }
            .confirmationDialog("Iniciar sesión con", isPresented: $showSignInProviders) {
                Button("Google") { startSignIn(provider: "google") }
                Button("GitHub") { startSignIn(provider: "github") }
                Button("Cancelar", role: .cancel) {}
            }
            .alert("No se pudo iniciar sesión", isPresented: Binding(
                get: { accountError != nil },
                set: { if !$0 { accountError = nil } }
            )) {
                Button("Aceptar", role: .cancel) {}
            } message: {
                Text(accountError ?? "")
            }
        }
    }

    private var versionDescription: String {
        let version = Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0.0"
        let build = Bundle.main.object(forInfoDictionaryKey: "CFBundleVersion") as? String ?? "42"
        return "\(version) (\(build))"
    }

    private var notificationStatusLabel: String {
        switch notificationStatus {
        case .authorized: return "Permitidas"
        case .provisional: return "Provisionales"
        case .ephemeral: return "Temporales"
        case .denied: return "Desactivadas"
        case .notDetermined: return "Sin solicitar"
        @unknown default: return "Desconocido"
        }
    }

    private var locationStatusLabel: String {
        switch locationManager.authorizationStatus {
        case .authorizedAlways: return "Siempre"
        case .authorizedWhenInUse: return "Al usar la app"
        case .denied, .restricted: return "Desactivada"
        case .notDetermined: return "Sin solicitar"
        @unknown default: return "Desconocida"
        }
    }

    private func saveAlertPreferences() {
        Task { await state.applyAlertPreferences() }
    }

    private func refreshHistory() {
        Task { await state.refreshData() }
    }

    private func runAlertTest() {
        if showsCloseButton {
            dismiss()
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.3) {
                state.runAlertSimulation()
            }
        } else {
            state.runAlertSimulation()
        }
    }

    private func requestNotificationPermission() {
        Task {
            notificationStatus = await state.requestNotificationPermission()
            if notificationStatus == .denied,
               let url = URL(string: UIApplication.openSettingsURLString) {
                _ = await UIApplication.shared.open(url)
            }
        }
    }

    private func openSystemSettings() {
        guard let url = URL(string: UIApplication.openSettingsURLString) else { return }
        Task { _ = await UIApplication.shared.open(url) }
    }

    private func startSignIn(provider: String) {
        SeismikOAuthSignIn.shared.start(provider: provider) { result in
            DispatchQueue.main.async {
                switch result {
                case let .success(identity):
                    self.account = identity
                    Task { await state.accountDidSignIn(identity) }
                case let .failure(error): self.accountError = error.localizedDescription
                }
            }
        }
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

// MARK: - Búsqueda de familiares (iPhone nativo)

/// Tras un sismo cada integrante avisa si está bien o necesita ayuda. Ese toque
/// comparte su ubicación con el círculo durante unas horas y avisa a los demás.
/// La cuenta identifica a cada persona; nada se comparte sin tocar un botón.
public struct FamilySafetyView: View {
    public let showsCloseButton: Bool
    @Environment(\.dismiss) private var dismiss
    @ObservedObject private var locationManager = LocationManager.shared
    @ObservedObject private var appState = SeismikState.shared

    @State private var circle: FamilyCircle?
    @State private var isLoading = false
    @State private var isReporting = false
    @State private var displayName = ""
    @State private var circleName = "Mi familia"
    @State private var inviteCode = ""
    @State private var precise = false
    @State private var message: String?
    @State private var region = MKCoordinateRegion(
        center: CLLocationCoordinate2D(latitude: 4.65, longitude: -74.05),
        span: MKCoordinateSpan(latitudeDelta: 4.0, longitudeDelta: 4.0)
    )

    public init(showsCloseButton: Bool = true) {
        self.showsCloseButton = showsCloseButton
    }

    public var body: some View {
        CompatibleNavigationStack {
            Group {
                if appState.account == nil {
                    signInContent
                } else if isLoading && circle == nil {
                    ProgressView("Cargando tu familia…")
                } else if let circle {
                    circleContent(circle)
                } else {
                    enrollmentContent
                }
            }
            .navigationTitle("Familia")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    if showsCloseButton {
                        Button("Listo") { dismiss() }
                    }
                }
            }
            .task(id: appState.account?.uid) { await reload() }
            .onChange(of: appState.familyUpdates) { _ in
                Task { await reload() }
            }
            .alert("Familia", isPresented: Binding(
                get: { message != nil }, set: { if !$0 { message = nil } }
            )) {
                Button("Aceptar", role: .cancel) {}
            } message: {
                Text(message ?? "")
            }
        }
    }

    private var signInContent: some View {
        ScrollView {
            VStack(spacing: 18) {
                Image(systemName: "person.2.wave.2.fill")
                    .font(.system(size: 44, weight: .medium))
                    .foregroundColor(SeismikColors.systemBlue)
                    .padding(.top, 24)
                Text("Avísale a tu familia que estás bien")
                    .font(.title2.weight(.bold))
                    .multilineTextAlignment(.center)
                Text("Tras un sismo, cada integrante de tu círculo reporta si está bien o necesita ayuda. Ese reporte comparte su ubicación con la familia durante unas horas y les llega como notificación.")
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                Text("Para saber quién es quién necesitas iniciar sesión. Seismik nunca comparte tu ubicación sin que toques un botón.")
                    .font(.footnote)
                    .foregroundColor(.secondary)
                    .multilineTextAlignment(.center)
                Button {
                    signIn(provider: "google")
                } label: {
                    Label("Iniciar sesión con Google", systemImage: "person.badge.key.fill")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
                .padding(.top, 8)
                Button("Iniciar sesión con GitHub") { signIn(provider: "github") }
                    .font(.footnote)
            }
            .padding(24)
        }
    }

    private var enrollmentContent: some View {
        Form {
            Section {
                Label("Hola, \(firstName)", systemImage: "hand.wave.fill")
                    .foregroundColor(SeismikColors.systemBlue)
                Text("Crea el círculo de tu familia o únete con el código que te envió quien lo creó. Cada código sirve una sola vez y vence en 24 horas.")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Section("Crear círculo") {
                TextField("Cómo te verá tu familia", text: $displayName)
                TextField("Nombre del círculo", text: $circleName)
                Button("Crear círculo") { Task { await createCircle() } }
                    .disabled(trimmed(displayName).isEmpty)
            }
            Section("Unirse con invitación") {
                TextField("Código de invitación", text: $inviteCode)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                TextField("Cómo te verá tu familia", text: $displayName)
                Button("Unirme al círculo") { Task { await joinCircle() } }
                    .disabled(trimmed(inviteCode).isEmpty || trimmed(displayName).isEmpty)
            }
            Section {
                Button("Cerrar sesión", role: .destructive) {
                    Task { await appState.signOutAccount() }
                }
            }
        }
        .onAppear {
            if displayName.isEmpty { displayName = firstName }
        }
    }

    private func circleContent(_ circle: FamilyCircle) -> some View {
        Form {
            Section {
                VStack(alignment: .leading, spacing: 10) {
                    Text(appState.pendingFamilyCheckIn == nil ? "¿Estás bien?" : "Tras el sismo, ¿estás bien?")
                        .font(.title3.weight(.bold))
                    if let event = appState.pendingFamilyCheckIn {
                        Text(eventLabel(event))
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                    }
                    if let last = circle.members.first(where: { $0.isYou })?.status {
                        Text("Tu último aviso: \(last.needsHelp ? "necesitas ayuda" : "estás bien") · \(ago(last.reportedAt))")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                    HStack(spacing: 10) {
                        Button {
                            Task { await report(needsHelp: false) }
                        } label: {
                            Label("Estoy bien", systemImage: "checkmark.circle.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.green)

                        Button {
                            Task { await report(needsHelp: true) }
                        } label: {
                            Label("Necesito ayuda", systemImage: "exclamationmark.triangle.fill")
                                .frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(.red)
                    }
                    .controlSize(.large)
                    .disabled(isReporting)
                    Toggle("Compartir ubicación precisa", isOn: $precise)
                    Text("Tu ubicación se comparte con tu familia durante 4 horas y luego se borra. Sin la precisa ven una zona aproximada.")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .padding(.vertical, 4)
            }

            let located = circle.members.filter { $0.location != nil }
            if !located.isEmpty {
                Section("Mapa de tu familia") {
                    Map(coordinateRegion: $region, annotationItems: located) { member in
                        MapMarker(
                            coordinate: CLLocationCoordinate2D(
                                latitude: member.location!.latitude,
                                longitude: member.location!.longitude
                            ),
                            tint: member.status == nil ? .blue : statusColor(member.status)
                        )
                    }
                    .frame(height: 240)
                    .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
            }

            Section("Integrantes de \(circle.circleName)") {
                ForEach(circle.members) { member in
                    HStack(spacing: 12) {
                        Image(systemName: statusSymbol(member.status))
                            .font(.title3)
                            .foregroundColor(statusColor(member.status))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(member.isYou ? "\(member.displayName) · Tú" : member.displayName)
                            Text(statusLabel(member.status))
                                .font(.caption)
                                .foregroundColor(.secondary)
                            if let note = member.status?.message {
                                Text("«\(note)»")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            Text(locationLabel(member.location))
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }
                if circle.isOwner == true {
                    Button("Crear y copiar invitación") { Task { await createInvitation() } }
                }
            }

            Section(footer: Text("Seismik no sustituye a los servicios de emergencia. Si alguien está en peligro, llama a la línea de emergencias de tu país.")) {
                Button("Dejar de compartir mi ubicación", role: .destructive) {
                    Task { await stopSharing() }
                }
                Button("Cerrar sesión", role: .destructive) {
                    Task {
                        await appState.signOutAccount()
                        self.circle = nil
                    }
                }
            }
        }
    }

    private var firstName: String {
        let name = appState.account?.name.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if let first = name.split(separator: " ").first { return String(first) }
        return appState.account?.email.components(separatedBy: "@").first ?? ""
    }

    private func trimmed(_ value: String) -> String {
        value.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    private func statusSymbol(_ status: FamilyStatus?) -> String {
        guard let status else { return "questionmark.circle" }
        return status.needsHelp ? "exclamationmark.triangle.fill" : "checkmark.circle.fill"
    }

    private func statusColor(_ status: FamilyStatus?) -> Color {
        guard let status else { return .secondary }
        return status.needsHelp ? .red : .green
    }

    private func statusLabel(_ status: FamilyStatus?) -> String {
        guard let status else { return "Sin aviso reciente" }
        return "\(status.needsHelp ? "Necesita ayuda" : "Está bien") · \(ago(status.reportedAt))"
    }

    private func locationLabel(_ location: FamilyLocation?) -> String {
        guard let location else { return "No comparte ubicación" }
        return location.precision == "precise" ? "Ubicación precisa" : "Ubicación aproximada"
    }

    private func ago(_ iso: String?) -> String {
        guard let iso else { return "hace un momento" }
        // El servidor envía microsegundos, que ISO8601DateFormatter no admite.
        let normalized = iso.replacingOccurrences(of: "\\.[0-9]+", with: "", options: .regularExpression)
        guard let date = ISO8601DateFormatter().date(from: normalized) else { return "hace un momento" }
        let minutes = Int(Date().timeIntervalSince(date) / 60)
        if minutes < 1 { return "hace un momento" }
        if minutes < 60 { return "hace \(minutes) min" }
        if minutes < 1_440 { return "hace \(minutes / 60) h" }
        return "hace \(minutes / 1_440) d"
    }

    private func eventLabel(_ event: SeismicEvent) -> String {
        let magnitude = event.magnitude.map { String(format: "M %.1f", $0) } ?? "Sismo"
        guard let place = event.place else { return magnitude }
        return "\(magnitude) · \(place)"
    }

    private func signIn(provider: String) {
        SeismikOAuthSignIn.shared.start(provider: provider) { result in
            DispatchQueue.main.async {
                switch result {
                case let .success(identity):
                    Task { await appState.accountDidSignIn(identity) }
                case let .failure(error):
                    // Cerrar la hoja de inicio de sesión no es un error que mostrar.
                    if let authError = error as? ASWebAuthenticationSessionError,
                       authError.code == .canceledLogin {
                        return
                    }
                    message = "No se pudo iniciar sesión. Revisa tu conexión e inténtalo de nuevo."
                }
            }
        }
    }

    private func reload() async {
        guard appState.account != nil else {
            circle = nil
            return
        }
        isLoading = true
        defer { isLoading = false }
        do {
            circle = try await SeismikAPIClient.shared.fetchFamilyCircle()
            if let first = circle?.members.first(where: { $0.location != nil })?.location {
                region.center = CLLocationCoordinate2D(latitude: first.latitude, longitude: first.longitude)
            }
        } catch SeismikAPIError.accountRequired {
            appState.accountSessionExpired()
        } catch let SeismikAPIError.rejected(status, _) where status == 401 {
            appState.accountSessionExpired()
            message = "Tu sesión venció. Inicia sesión de nuevo para ver a tu familia."
        } catch {
            message = "No se pudo cargar tu familia ahora. Revisa tu conexión e inténtalo de nuevo."
        }
    }

    private func report(needsHelp: Bool) async {
        isReporting = true
        defer { isReporting = false }
        locationManager.requestPermission()
        let coordinate = locationManager.currentCoordinate
        do {
            try await SeismikAPIClient.shared.reportFamilyStatus(
                needsHelp: needsHelp,
                eventId: appState.pendingFamilyCheckIn?.id,
                latitude: coordinate?.latitude,
                longitude: coordinate?.longitude,
                precise: precise
            )
            appState.pendingFamilyCheckIn = nil
            if coordinate == nil {
                message = "Aviso enviado sin ubicación. Permite la ubicación para compartirla con tu familia."
            } else {
                message = needsHelp
                    ? "Tu familia sabe que necesitas ayuda y ve dónde estás."
                    : "Tu familia sabe que estás bien."
            }
            await reload()
        } catch let SeismikAPIError.rejected(status, _) where status == 401 {
            appState.accountSessionExpired()
            message = "Tu sesión venció. Inicia sesión de nuevo para avisar a tu familia."
        } catch {
            message = "No se pudo enviar el aviso. Revisa tu conexión e inténtalo otra vez."
        }
    }

    private func createCircle() async {
        do {
            try await SeismikAPIClient.shared.createFamilyCircle(displayName: displayName, circleName: circleName)
            await reload()
        } catch { message = "No se pudo crear el círculo. Inténtalo otra vez." }
    }

    private func joinCircle() async {
        do {
            try await SeismikAPIClient.shared.joinFamilyCircle(inviteCode: inviteCode, displayName: displayName)
            await reload()
        } catch { message = "El código no es válido, ya venció o tu cuenta ya está en un círculo." }
    }

    private func createInvitation() async {
        do {
            let code = try await SeismikAPIClient.shared.createFamilyInvitation(displayName: "Familiar")
            UIPasteboard.general.string = code
            message = "Invitación copiada. Vence en 24 horas y sirve una sola vez."
        } catch { message = "Sólo quien creó el círculo puede invitar." }
    }

    private func stopSharing() async {
        do {
            try await SeismikAPIClient.shared.stopSharingFamilyLocation()
            await reload()
        } catch { message = "No se pudo borrar tu ubicación. Revisa tu conexión." }
    }
}
