import 'package:url_launcher/url_launcher.dart';

/// Abre enlaces web en la superficie integrada del sistema.
///
/// En Android, [LaunchMode.inAppBrowserView] usa Chrome Custom Tabs cuando
/// Chrome (u otro navegador compatible) está disponible. En iOS usa la vista
/// Safari integrada. La persona permanece en Seismik y vuelve con Atrás.
Future<bool> openWebLink(Uri uri) {
  if (uri.scheme != 'https' && uri.scheme != 'http') {
    return Future<bool>.value(false);
  }
  return launchUrl(uri, mode: LaunchMode.inAppBrowserView);
}
