import Foundation
import UserNotifications

/// Presenta las alertas sísmicas aunque la app esté en primer plano.
///
/// Por omisión iOS silencia una notificación cuando su app ya está abierta.
/// Para un aviso de sismo eso es justo lo contrario de lo que hace falta: quien
/// tiene la app abierta es quien más rápido puede reaccionar.
///
/// Va en su propia clase, y no en `AppDelegate`, porque `FlutterAppDelegate` ya
/// adopta `UNUserNotificationCenterDelegate` y sobrescribir sus métodos ataría
/// este comportamiento a los detalles internos del motor de Flutter, que esta
/// app ya no usa para dibujar.
public final class SeismikNotificationPresenter: NSObject, UNUserNotificationCenterDelegate {
    public static let shared = SeismikNotificationPresenter()

    /// Respect the server's per-device decision, including stale official reports.
    static func shouldPresentAlarm(for event: SeismicEvent) -> Bool {
        if let critical = event.critical { return critical }
        return event.isPreliminary // Compatibility with older early-warning payloads.
    }

    static func alertTitle(for event: SeismicEvent) -> String {
        event.isCriticalOfficial ? "SISMO FUERTE EN TU ZONA" : "ALERTA SÍSMICA"
    }

    static func alertInstruction(for event: SeismicEvent) -> String {
        event.isCriticalOfficial ? "Revisa a tu familia y prepárate para réplicas" : "PROTÉGETE AHORA"
    }

    static func elapsedDescription(for event: SeismicEvent, now: Date = Date()) -> String {
        guard let origin = event.detectedAt else { return "Hora del sismo no disponible" }
        return "Hace \(max(0, Int(now.timeIntervalSince(origin) / 60))) min · desde el sismo"
    }

    private override init() {
        super.init()
    }

    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
        Task { @MainActor in
            SeismikState.shared.handleRemoteNotification(
                notification.request.content.userInfo
            )
        }
        completionHandler([.banner, .list, .sound])
    }

    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        didReceive response: UNNotificationResponse,
        withCompletionHandler completionHandler: @escaping () -> Void
    ) {
        // Al tocar el aviso, la app sincroniza para mostrar el sismo que lo
        // originó incluso si el push llegó mientras estaba cerrada.
        Task { @MainActor in
            SeismikState.shared.handleRemoteNotification(
                response.notification.request.content.userInfo,
                opened: true
            )
            await SeismikState.shared.syncMissedAlerts()
            await SeismikState.shared.refreshData()
            completionHandler()
        }
    }
}
