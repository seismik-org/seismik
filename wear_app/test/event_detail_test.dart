import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik_wear/event.dart';
import 'package:seismik_wear/event_detail_screen.dart';
import 'package:seismik_wear/main.dart';

/// El detalle lleva a la muñeca la comparación del teléfono en una pantalla de
/// 426 px: cada organización con su valor y escala, legible y sin desbordar.
void main() {
  const Size watchScreen = Size(426, 426);

  WearEvent grouped() => WearEvent.fromMap(<String, dynamic>{
    'event_id': 'sgc_colombia:1',
    'type': 'official_report_update',
    'origin_time': DateTime.now()
        .toUtc()
        .subtract(const Duration(minutes: 8))
        .toIso8601String(),
    'magnitude': 4.2,
    'depth_km': 12.0,
    'place': 'Los Santos, Santander',
    'source_reports': <Map<String, dynamic>>[
      <String, dynamic>{
        'agency': 'Servicio Geológico Colombiano',
        'magnitude': 4.2,
        'magnitude_type': 'ML',
        'review_status': 'automatic',
      },
      <String, dynamic>{
        'agency': 'USGS',
        'magnitude': 3.13,
        'magnitude_type': 'Mw',
        'review_status': 'reviewed',
      },
    ],
  });

  Future<void> show(WidgetTester tester, WearEvent event) async {
    tester.view.physicalSize = watchScreen;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: WearEventDetailScreen(event: event, accent: Colors.blue),
      ),
    );
  }

  testWidgets('muestra cada organización con su magnitud y escala', (
    WidgetTester tester,
  ) async {
    await show(tester, grouped());

    expect(find.text('Magnitudes por organización'), findsOneWidget);
    expect(find.textContaining('No se promedian'), findsOneWidget);
    expect(find.text('Servicio Geológico Colombiano'), findsOneWidget);
    expect(find.text('ML · automatic'), findsOneWidget);
    expect(find.text('4.2'), findsWidgets);
    expect(find.text('USGS'), findsOneWidget);
    expect(find.text('Mw · reviewed'), findsOneWidget);
    // La precisión original se conserva en la comparación.
    expect(find.text('3.13'), findsOneWidget);
    expect(find.text('3.1'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('un sismo de una sola fuente se muestra con su organización', (
    WidgetTester tester,
  ) async {
    await show(
      tester,
      WearEvent.fromMap(<String, dynamic>{
        'event_id': 'sgc_colombia:2',
        'origin_time': '2026-10-12T12:00:00Z',
        'magnitude': 3.7,
        'agency': 'SGC',
      }),
    );

    expect(find.text('SGC'), findsOneWidget);
    expect(find.text('3.7'), findsWidgets);
    expect(find.text('Sin estado de revisión'), findsOneWidget);
  });

  testWidgets('un reporte sin magnitud dice que no la tiene', (
    WidgetTester tester,
  ) async {
    await show(
      tester,
      WearEvent.fromMap(<String, dynamic>{
        'event_id': 'x',
        'origin_time': '2026-10-12T12:00:00Z',
        'source_reports': <Map<String, dynamic>>[
          <String, dynamic>{'agency': 'EMSC'},
        ],
      }),
    );

    expect(find.text('Sin magnitud'), findsOneWidget);
    expect(find.text('EMSC'), findsOneWidget);
  });

  testWidgets('tocar un sismo de la lista abre su detalle', (
    WidgetTester tester,
  ) async {
    tester.view.physicalSize = watchScreen;
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      MaterialApp(
        theme: ThemeData.dark(),
        home: Scaffold(
          body: OpensEventDetail(event: grouped(), child: const Text('fila')),
        ),
      ),
    );

    await tester.tap(find.text('fila'));
    await tester.pumpAndSettle();

    expect(find.byType(WearEventDetailScreen), findsOneWidget);
    expect(find.text('USGS'), findsOneWidget);
  });
}
