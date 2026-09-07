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

    private override init() {
        super.init()
    }

    public func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification,
        withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
    ) {
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
            await SeismikState.shared.syncMissedAlerts()
            await SeismikState.shared.refreshData()
            completionHandler()
        }
    }
}
