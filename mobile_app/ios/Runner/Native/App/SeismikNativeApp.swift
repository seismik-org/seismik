import SwiftUI

/// Raíz de la aplicación nativa en SwiftUI de Seismik para iPhone.
public struct SeismikNativeAppRoot: View {
    @StateObject private var state = SeismikState.shared
    @State private var selectedTab = 0
    @Environment(\.scenePhase) private var scenePhase

    public init() {}

    public var body: some View {
        TabView(selection: $selectedTab) {
            MonitorView()
                .tabItem {
                    Label("Historial", systemImage: "clock.arrow.circlepath")
                }
                .tag(0)

            FeltReportView(preselectedEvent: state.events.first, showsCloseButton: false)
                .tabItem {
                    Label("Sismo sentido", systemImage: "waveform.path.ecg")
                }
                .tag(1)

            DamageReportView(preselectedEvent: state.events.first, showsCloseButton: false)
                .tabItem {
                    Label("Daños", systemImage: "house.fill")
                }
                .tag(2)

            FamilySafetyView(showsCloseButton: false)
                .tabItem {
                    Label("Familia", systemImage: "person.2.fill")
                }
                .tag(3)

            SettingsView(state: state, showsCloseButton: false)
                .tabItem {
                    Label("Configuración", systemImage: "slider.horizontal.3")
                }
                .tag(4)
        }
        .onOpenURL { url in
            guard url.scheme == "seismik" else { return }
            switch url.host {
            case "history", "map": selectedTab = 0
            case "felt", "sentido": selectedTab = 1
            case "damage", "danos": selectedTab = 2
            case "settings", "configuracion": selectedTab = 4
            case "family", "familia": selectedTab = 3
            default: selectedTab = 0
            }
        }
        .onChange(of: state.requestedTab) { tab in
            guard let tab else { return }
            selectedTab = tab
            state.requestedTab = nil
        }
        .onAppear {
            // A tapped family push can arrive before SwiftUI installs onChange.
            if let tab = state.requestedTab {
                selectedTab = tab
                state.requestedTab = nil
            }
        }
        .overlay {
            // The alarm and family check-in must be reachable from every tab.
            if let alertEvent = state.activeAlert {
                EmergencyAlertView(
                    event: alertEvent,
                    onDismiss: { state.dismissAlert() },
                    onReportSafe: { state.requestFamilyCheckIn(for: alertEvent) }
                )
                .transition(.opacity.combined(with: .scale(scale: 0.96)))
            }
        }
        .onChange(of: scenePhase) { phase in
            guard phase == .active else { return }
            Task {
                await state.updateRegistration()
                await state.refreshData()
            }
        }
        .task {
            while !Task.isCancelled {
                do { try await Task.sleep(nanoseconds: 15_000_000_000) }
                catch { break }
                if UIApplication.shared.applicationState == .active {
                    await state.refreshIfStale()
                }
            }
        }
        // Lo primero que ve una persona nueva: los permisos que una alerta necesita para llegar, pedidos de entrada
        // y no escondidos en Configuración.
        .task { await state.evaluatePermissionsOnboarding() }
        .fullScreenCover(isPresented: $state.showPermissionsOnboarding) {
            PermissionsOnboardingView(state: state)
        }
    }
}

/// Bienvenida con los permisos esenciales. «Activar ahora» dispara los diálogos del sistema en orden:
/// notificaciones y alertas críticas, y ubicación. «Ahora no» la cierra sin pedir nada; vuelve a aparecer en la
/// siguiente apertura mientras la persona no haya decidido, y deja de insistir en cuanto concede o niega.
struct PermissionsOnboardingView: View {
    @ObservedObject var state: SeismikState
    @State private var working = false

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Spacer(minLength: 16)
            Image(systemName: "bell.badge.fill")
                .font(.system(size: 46))
                .foregroundColor(.red)
            Text("Activa lo esencial para que la alerta te llegue")
                .font(.title.bold())
            Text("Seismik avisa en segundos. Para que el aviso suene aunque el teléfono esté en silencio o con un modo de concentración, necesita estos permisos desde el principio.")
                .font(.body)
                .foregroundColor(.secondary)
            permissionRow(
                icon: "bell.and.waves.left.and.right.fill",
                title: "Notificaciones y alertas críticas",
                text: "Suenan con el teléfono en silencio y los simulacros llegan como una alerta real. iPhone te preguntará dos veces: acepta ambas."
            )
            permissionRow(
                icon: "location.fill",
                title: "Ubicación mientras usas la app",
                text: "Calcula si la sacudida fuerte te alcanza. Se comparte aproximada por defecto."
            )
            Spacer()
            Button {
                Task {
                    working = true
                    await state.requestEssentialPermissions()
                    working = false
                }
            } label: {
                Text(working ? "Solicitando…" : "Activar ahora")
                    .font(.headline)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.red)
                    .foregroundColor(.white)
                    .cornerRadius(14)
            }
            .disabled(working)
            Button("Ahora no") { state.finishPermissionsOnboarding() }
                .frame(maxWidth: .infinity)
                .foregroundColor(.secondary)
            Text("Si ya los negaste, puedes cambiarlos en Configuración > Alertas críticas.")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(24)
        .interactiveDismissDisabled()
    }

    private func permissionRow(icon: String, title: String, text: String) -> some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: icon)
                .font(.system(size: 22))
                .frame(width: 30)
                .foregroundColor(.red)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).font(.headline)
                Text(text).font(.subheadline).foregroundColor(.secondary)
            }
        }
    }
}
