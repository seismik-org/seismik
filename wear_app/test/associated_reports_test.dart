import 'package:flutter_test/flutter_test.dart';
import 'package:seismik_wear/event.dart';

/// Un solo elemento por sismo y cada organización con su valor y escala.
void main() {
  Map<String, dynamic> grouped({String id = 'sgc_colombia:1'}) =>
      <String, dynamic>{
        'event_id': id,
        'type': 'official_report_update',
        'origin_time': '2026-10-12T12:00:00Z',
        'magnitude': 4.2,
        'place': 'Los Santos, Santander',
        'related_event_ids': <String>['sgc_colombia:1', 'usgs_global:9'],
        'source_reports': <Map<String, dynamic>>[
          <String, dynamic>{
            'event_id': 'sgc_colombia:1',
            'agency': 'SGC',
            'magnitude': 4.2,
            'magnitude_type': 'ML',
            'review_status': 'automatic',
          },
          <String, dynamic>{
            'event_id': 'usgs_global:9',
            'agency': 'USGS',
            'magnitude': 3.13,
            'magnitude_type': 'Mw',
            'review_status': 'reviewed',
          },
        ],
      };

  test('los reportes por organización conservan valor, escala y revisión', () {
    final WearEvent event = WearEvent.fromMap(grouped());

    expect(event.sourceReports.length, 2);
    expect(event.sourceReports[0].magnitudeType, 'ML');
    expect(event.sourceReports[1].magnitudeType, 'Mw');
    expect(event.sourceReports[1].reviewStatus, 'reviewed');
    // 3.13 no se convierte en 3.1 al compararlo.
    expect(event.sourceReports[1].valueLabel, '3.13');
    expect(event.sourceReports[0].valueLabel, '4.2');
    expect(event.relatedEventIds, <String>['sgc_colombia:1', 'usgs_global:9']);
  });

  test('un entero del servidor lleva su decimal y un texto se respeta', () {
    final WearSourceReport whole = WearSourceReport.fromMap(<String, dynamic>{
      'agency': 'EMSC',
      'magnitude': 4,
    });
    final WearSourceReport text = WearSourceReport.fromMap(<String, dynamic>{
      'agency': 'EMSC',
      'magnitude': ' 3.10 ',
    });

    expect(whole.valueLabel, '4.0');
    expect(text.valueLabel, '3.10');
  });

  test('un reporte sin magnitud no inventa un número', () {
    final WearSourceReport report = WearSourceReport.fromMap(<String, dynamic>{
      'source_id': 'emsc_global',
      'magnitude': null,
    });

    expect(report.agency, 'emsc_global');
    expect(report.valueLabel, 'Sin magnitud');
  });

  test('un evento anterior al contrato no trae reportes y sigue leyéndose', () {
    final WearEvent event = WearEvent.fromMap(<String, dynamic>{
      'event_id': 'old',
      'origin_time': '2026-10-12T12:00:00Z',
      'magnitude': 4.1,
    });

    expect(event.sourceReports, isEmpty);
    expect(event.relatedEventIds, isEmpty);
    expect(event.magnitudeLabel, '4.1');
  });

  test('datos mal formados no tumban la lista', () {
    final WearEvent event = WearEvent.fromMap(<String, dynamic>{
      'event_id': 'x',
      'source_reports': 'no es una lista',
      'related_event_ids': <Object?>[null, '', 7],
    });

    expect(event.sourceReports, isEmpty);
    expect(event.relatedEventIds, <String>['7']);
  });

  test('un mismo sismo con otro identificador no aparece dos veces', () {
    // Caché de una versión anterior: el sismo de USGS y el de SGC por separado.
    final List<WearEvent> events = WearEvent.parseList(<Object?>[
      grouped(),
      <String, dynamic>{
        'event_id': 'usgs_global:9',
        'origin_time': '2026-10-12T12:00:08Z',
        'magnitude': 3.13,
      },
      <String, dynamic>{
        'event_id': 'sgc_colombia:2',
        'origin_time': '2026-10-12T11:00:00Z',
        'magnitude': 3.0,
      },
      'basura',
    ]);

    expect(events.map((WearEvent e) => e.id), <String>[
      'sgc_colombia:1',
      'sgc_colombia:2',
    ]);
  });

  test('una lista que no es lista queda vacía', () {
    expect(WearEvent.parseList(null), isEmpty);
    expect(WearEvent.parseList(<String, dynamic>{}), isEmpty);
  });
}
