import Flutter
import GoogleMaps
import UIKit
import UserNotifications
import SwiftUI

@main
@objc class AppDelegate: FlutterAppDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    if let mapsKey = Bundle.main.object(forInfoDictionaryKey: "SeismikGoogleMapsAPIKey") as? String,
       !mapsKey.isEmpty,
       !mapsKey.hasPrefix("$(") {
      GMSServices.provideAPIKey(mapsKey)
    }
    GeneratedPluginRegistrant.register(with: self)
    let launched = super.application(application, didFinishLaunchingWithOptions: launchOptions)

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
}

