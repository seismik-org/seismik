import SwiftUI

/// Raíz de la aplicación nativa en SwiftUI de Seismik para iPhone.
public struct SeismikNativeAppRoot: View {
    @StateObject private var state = SeismikState.shared
    @State private var selectedTab = 0

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

            SettingsView(state: state, showsCloseButton: false)
                .tabItem {
                    Label("Configuración", systemImage: "slider.horizontal.3")
                }
                .tag(3)
        }
        .tint(SeismikColors.systemBlue)
        .onOpenURL { url in
            guard url.scheme == "seismik" else { return }
            switch url.host {
            case "history", "map": selectedTab = 0
            case "felt", "sentido": selectedTab = 1
            case "damage", "danos": selectedTab = 2
            case "settings", "configuracion": selectedTab = 3
            default: selectedTab = 0
            }
        }
    }
}
