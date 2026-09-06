import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:seismik/data/models/citizen_report.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/presentation/screens/report_result_screen.dart';
import 'package:seismik/presentation/widgets/open_in_maps_button.dart';
import 'package:seismik/services/map_launcher.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';

SeismicEvent event({double? latitude, double? longitude}) =>
    SeismicEvent.fromMap(<String, dynamic>{
      'event_id': 'event-1',
      'type': 'official_report_update',
      'origin_time': '2026-08-30T12:00:00Z',
      'latitude': latitude,
      'longitude': longitude,
      'place': 'Cundinamarca',
    });

Widget wrap(MobileSettings settings, Widget child) =>
    ChangeNotifierProvider<MobileSettings>.value(
      value: settings,
      child: MaterialApp(home: Scaffold(body: child)),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MobileSettings settings;

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    settings = MobileSettings();
    await settings.load();
  });

  testWidgets('la etiqueta refleja el proveedor elegido', (tester) async {
    await tester.pumpWidget(
      wrap(settings, OpenInMapsButton(event: event(latitude: 4.65, longitude: -74.05))),
    );
    expect(find.text('Abrir epicentro en mapas'), findsOneWidget);

    await settings.setMapProvider(MapProvider.apple);
    await tester.pumpAndSettle();
    // El runner es Windows/Android: Apple Maps no existe allí, por lo que el
    // botón se presenta como el manejador de mapas disponible.
    expect(find.text('Abrir epicentro en mapas'), findsOneWidget);

    await settings.setMapProvider(MapProvider.google);
    await tester.pumpAndSettle();
    expect(find.text('Abrir en Google Maps'), findsOneWidget);
  });

  testWidgets('un evento sin epicentro no ofrece la acción', (tester) async {
    await tester.pumpWidget(wrap(settings, OpenInMapsButton(event: event())));
    expect(find.byType(OutlinedButton), findsNothing);
  });

  testWidgets('al tocar se abre el epicentro del sismo', (tester) async {
    final List<Uri> opened = <Uri>[];
    Future<bool> opener(Uri uri, {LaunchMode mode = LaunchMode.platformDefault}) async {
      opened.add(uri);
      return true;
    }

    await tester.pumpWidget(
      wrap(
        settings,
        OpenInMapsButton(
          event: event(latitude: 4.65, longitude: -74.05),
          launcher: MapLauncher(opener: opener, isApplePlatform: false),
        ),
      ),
    );
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();

    expect(opened, hasLength(1));
    expect(opened.single.toString(), contains('4.65,-74.05'));
  });

  testWidgets('sin app de mapas se avisa a la persona', (tester) async {
    Future<bool> opener(Uri uri, {LaunchMode mode = LaunchMode.platformDefault}) async =>
        false;

    await tester.pumpWidget(
      wrap(
        settings,
        OpenInMapsButton(
          event: event(latitude: 4.65, longitude: -74.05),
          launcher: MapLauncher(opener: opener, isApplePlatform: false),
        ),
      ),
    );
    await tester.tap(find.byType(OutlinedButton));
    await tester.pumpAndSettle();

    expect(
      find.text('No hay una aplicación de mapas disponible.'),
      findsOneWidget,
    );
  });

  testWidgets('un reporte guardado sin conexión se comunica como tal', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        home: ReportResultScreen(
          result: ReportResult.queued(
            reportId: 'report-1',
            locationPrecision: 'approximate',
            emergencyActionRecommended: false,
          ),
        ),
      ),
    );

    expect(find.text('Reporte guardado'), findsOneWidget);
    expect(find.text('Reporte guardado en el teléfono'), findsOneWidget);
    expect(find.byIcon(Icons.cloud_off_rounded), findsOneWidget);
    expect(find.textContaining('se enviará'), findsOneWidget);
  });

  testWidgets('un reporte aceptado conserva el mensaje de agradecimiento', (
    tester,
  ) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: ReportResultScreen(
          result: ReportResult(
            accepted: true,
            duplicate: false,
            reportId: 'report-2',
            locationPrecision: 'precise',
            emergencyActionRecommended: false,
            agencyRoutes: <AgencyRoute>[],
            notice: '',
          ),
        ),
      ),
    );

    expect(find.text('Reporte recibido'), findsOneWidget);
    expect(find.text('Gracias por reportar'), findsOneWidget);
  });
}
