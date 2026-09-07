import Flutter
import FirebaseAppCheck
import FirebaseCore
import GoogleMaps
import UIKit
import UserNotifications
import SwiftUI

@main
@objc class AppDelegate: FlutterAppDelegate {
  private let appCheckProviderFactory = SeismikAppCheckProviderFactory()

  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // La interfaz es SwiftUI nativa, por lo que no hay un `Firebase.initializeApp`
    // de Dart que configure App Check por nosotros. El proveedor debe instalarse
    // antes de crear la app Firebase para que el primer registro sea verificable.
    AppCheck.setAppCheckProviderFactory(appCheckProviderFactory)
    if FirebaseApp.app() == nil {
      FirebaseApp.configure()
    }

    if let mapsKey = Bundle.main.object(forInfoDictionaryKey: "SeismikGoogleMapsAPIKey") as? String,
       !mapsKey.isEmpty,
       !mapsKey.hasPrefix("$(") {
      GMSServices.provideAPIKey(mapsKey)
    }
    GeneratedPluginRegistrant.register(with: self)
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)

    if let notification = launchOptions?[.remoteNotification] as? [AnyHashable: Any] {
      Task { @MainActor in
        SeismikState.shared.handleRemoteNotification(notification)
      }
    }

    // Sin autorización, iOS descarta el contenido de la alerta aunque APNs
    // entregue el push: el token llega igual, pero la persona no ve nada. Es
    // el permiso que hace útil a toda la app, así que se pide al arrancar.
    UNUserNotificationCenter.current().delegate = SeismikNotificationPresenter.shared
    UNUserNotificationCenter.current().requestAuthorization(
      options: [.alert, .sound, .badge]
    ) { _, _ in
      // El token de APNs sirve aunque la persona rechace: permite avisos
      // silenciosos y deja el dispositivo registrado para cuando cambie de
      // opinión desde Ajustes.
      DispatchQueue.main.async {
        application.registerForRemoteNotifications()
      }
    }

    // La ventana la crea SceneDelegate: en un ciclo de vida basado en escenas,
    // una segunda ventana aquí queda huérfana y monta un segundo árbol SwiftUI.
    return launched
  }

  override func application(
    _ application: UIApplication,
    didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data
  ) {
    super.application(application, didRegisterForRemoteNotificationsWithDeviceToken: deviceToken)
    let tokenHex = deviceToken.map { String(format: "%02.2hhx", $0) }.joined()
    UserDefaults.standard.set(tokenHex, forKey: "seismik.apns_device_token")
    Task { @MainActor in
      await SeismikState.shared.updateRegistration()
    }
  }

  override func application(
    _ application: UIApplication,
    didReceiveRemoteNotification userInfo: [AnyHashable: Any],
    fetchCompletionHandler completionHandler: @escaping (UIBackgroundFetchResult) -> Void
  ) {
    Task { @MainActor in
      SeismikState.shared.handleRemoteNotification(userInfo)
      await SeismikState.shared.syncMissedAlerts()
      completionHandler(.newData)
    }
  }
}

/// DeviceCheck funciona desde iOS 11 y no exige una capacidad adicional en el
/// perfil de distribución. Firebase entrega al backend un token App Check real;
/// no se envían marcadores de prueba en TestFlight.
private final class SeismikAppCheckProviderFactory: NSObject, AppCheckProviderFactory {
  func createProvider(with app: FirebaseApp) -> AppCheckProvider? {
    DeviceCheckProvider(app: app)
  }
}
