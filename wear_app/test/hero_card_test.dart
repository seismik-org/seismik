import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik_wear/event.dart';
import 'package:seismik_wear/main.dart';

/// La pantalla del Pixel Watch mide 426 × 426. Si la tarjeta no cabe, hay que
/// desplazarse para leer lo más importante, que es justo lo que un reloj no
/// debería pedir. Estas pruebas miden la altura real, no la intención.
void main() {
  const Size watchScreen = Size(426, 426);

  WearEvent quake({
    double? magnitude = 4.6,
    double latitude = 6.80,
    double longitude = -73.10,
    String place = 'Los Santos, Santander',
    String type = 'official_report_update',
  }) => WearEvent.fromMap(<String, dynamic>{
    'event_id': 'sgc:1',
    'type': type,
    'origin_time': DateTime.now()
        .toUtc()
        .subtract(const Duration(minutes: 8))
        .toIso8601String(),
    'magnitude': magnitude,
    'depth_km': 12.0,
    'latitude': latitude,
    'longitude': longitude,
    'place': place,
  });

  Future<double> heightOf(WidgetTester tester, Widget card) async {
    tester.view.physicalSize = watchScreen;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          // Como en la app: dentro de la lista desplazable de la pantalla.
          body: ListView(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            children: <Widget>[card],
          ),
        ),
      ),
    );
    return tester.getSize(find.byType(HeroCard)).height;
  }

  testWidgets('la tarjeta cabe bajo el encabezado del reloj', (
    WidgetTester tester,
  ) async {
    final double height = await heightOf(
      tester,
      HeroCard(event: quake(), position: null),
    );

    // 426 menos el encabezado y el margen inferior deja unos 330 px útiles.
    expect(height, lessThan(300));
    expect(tester.takeException(), isNull);
  });

  testWidgets('un lugar largo se recorta en dos líneas, no crece sin fin', (
    WidgetTester tester,
  ) async {
    final double height = await heightOf(
      tester,
      HeroCard(
        event: quake(
          place: 'Medio San Juan (Andagoya) - Chocó, Colombia, a 47 km de',
        ),
        position: null,
      ),
    );

    expect(height, lessThan(300));
    expect(find.textContaining('Medio San Juan'), findsOneWidget);
  });

  testWidgets('sin magnitud ni ubicación la tarjeta sigue en pie', (
    WidgetTester tester,
  ) async {
    final double height = await heightOf(
      tester,
      HeroCard(
        event: quake(magnitude: null, type: 'earthquake_candidate'),
        position: null,
      ),
    );

    expect(height, lessThan(300));
    expect(find.text('—'), findsOneWidget);
    expect(find.text('preliminar'), findsOneWidget);
    expect(find.textContaining('Buscando tu ubicación'), findsOneWidget);
  });
}
