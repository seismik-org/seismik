import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/services/alert_memory.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/notification_service.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:seismik/state/seismik_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _QuietApi extends ApiClient {}

/// Un sismo real en Los Santos: detección preliminar, alerta del catálogo y
/// reporte oficial llegan por separado, con identificadores distintos.
Map<String, dynamic> _candidate({
  String id = 'cand-1',
  String at = '2026-09-19T20:00:05Z',
  double? latitude = 6.80,
  double? longitude = -73.10,
}) => <String, dynamic>{
  'type': 'earthquake_candidate',
  'event_id': id,
  'detected_at': at,
  'critical': 'true',
  if (latitude != null) 'estimated_latitude': '$latitude',
  if (longitude != null) 'estimated_longitude': '$longitude',
};

Map<String, dynamic> _official({
  String id = 'catalog:sgc_colombia:SGC2026abc:m52',
  String at = '2026-09-19T19:59:48Z',
  double latitude = 6.75,
  double longitude = -73.05,
}) => <String, dynamic>{
  'type': 'official_report_update',
  'event_id': id,
  'origin_time': at,
  'latitude': '$latitude',
  'longitude': '$longitude',
  'magnitude': '5.2',
  'place': 'Los Santos, Santander',
  'critical': 'true',
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final DateTime now = DateTime.utc(2026, 9, 19, 20, 5);

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test(
    'el reporte oficial de un sismo que ya sonó no vuelve a sonar',
    () async {
      final AlertMemory memory = AlertMemory();
      expect(await memory.alreadyRang(_candidate(), now: now), isFalse);

      await memory.remember(_candidate(), now: now);

      expect(
        await memory.alreadyRang(_official(), now: now),
        isTrue,
        reason: 'misma hora de origen y a pocos kilómetros: es el mismo sismo',
      );
      expect(
        await memory.alreadyRang(_candidate(), now: now),
        isTrue,
        reason: 'el mismo aviso, reenviado',
      );
    },
  );

  test('una réplica minutos después sí vuelve a sonar', () async {
    final AlertMemory memory = AlertMemory();
    await memory.remember(_candidate(), now: now);

    expect(
      await memory.alreadyRang(
        _candidate(id: 'cand-2', at: '2026-09-19T20:09:30Z'),
        now: now,
      ),
      isFalse,
    );
  });

  test('otro sismo lejano a la misma hora sí suena', () async {
    final AlertMemory memory = AlertMemory();
    await memory.remember(_candidate(), now: now);

    // Pasto está a unos 700 km de Los Santos.
    expect(
      await memory.alreadyRang(
        _official(id: 'usgs:us7000', latitude: 1.21, longitude: -77.28),
        now: now,
      ),
      isFalse,
    );
  });

  test(
    'una detección sin ubicar a la misma hora es el mismo movimiento',
    () async {
      final AlertMemory memory = AlertMemory();
      await memory.remember(_candidate(), now: now);

      expect(
        await memory.alreadyRang(
          _candidate(id: 'cand-3', latitude: null, longitude: null),
          now: now,
        ),
        isTrue,
      );
    },
  );

  test(
    'la prueba de alarma y los simulacros no silencian un sismo real',
    () async {
      final AlertMemory memory = AlertMemory();
      await memory.remember(
        _candidate(id: 'local-critical-test-1', at: '2026-09-19T20:00:00Z'),
        now: now,
      );
      await memory.remember(
        _candidate(id: 'drill-1', at: '2026-09-19T20:00:00Z'),
        now: now,
      );

      expect(await memory.alreadyRang(_candidate(), now: now), isFalse);
    },
  );

  test(
    'la memoria se comparte entre la app y el aviso en segundo plano',
    () async {
      await AlertMemory().remember(_candidate(), now: now);

      // Otra instancia, como la del isolate de Firebase.
      expect(await AlertMemory().alreadyRang(_official(), now: now), isTrue);
    },
  );

  test('una alarma de hace más de una hora se olvida', () async {
    final AlertMemory memory = AlertMemory();
    await memory.remember(_candidate(), now: now);

    expect(
      await memory.alreadyRang(
        _official(),
        now: now.add(const Duration(hours: 1, minutes: 1)),
      ),
      isFalse,
    );
  });

  test('un aviso sin hora ni identificador siempre suena', () async {
    final AlertMemory memory = AlertMemory();
    await memory.remember(_candidate(), now: now);

    expect(
      await memory.alreadyRang(<String, dynamic>{
        'type': 'earthquake_candidate',
      }),
      isFalse,
    );
  });

  group('pantalla de alarma', () {
    late SeismikState state;

    setUp(() {
      state = SeismikState(settings: MobileSettings(), apiClient: _QuietApi());
    });

    NotificationEnvelope alarm(Map<String, dynamic> data) =>
        NotificationEnvelope(event: SeismicEvent.fromMap(data), critical: true);

    NotificationEnvelope followUp(Map<String, dynamic> data) =>
        NotificationEnvelope(
          event: SeismicEvent.fromMap(data),
          critical: false,
          followUp: true,
        );

    test('«Cerrar» la quita y un aviso del mismo sismo no la reabre', () async {
      state.receiveNotification(alarm(_candidate()));
      expect(state.activeAlert?.id, 'cand-1');

      state.dismissAlert();
      expect(state.activeAlert, isNull);

      state.receiveNotification(followUp(_official()));

      expect(state.activeAlert, isNull, reason: 'ya se cerró: no vuelve');
      expect(
        state.officialEvent?.id,
        'catalog:sgc_colombia:SGC2026abc:m52',
        reason: 'los datos oficiales siguen llegando al aviso normal',
      );
    });

    test('con la pantalla abierta, un aviso del mismo sismo la actualiza', () {
      state.receiveNotification(alarm(_candidate()));
      state.receiveNotification(followUp(_official()));

      expect(state.activeAlert?.id, 'catalog:sgc_colombia:SGC2026abc:m52');
      expect(state.activeAlert?.magnitude, 5.2);
    });

    test('una réplica que sí suena vuelve a abrir la pantalla', () {
      state.receiveNotification(alarm(_candidate()));
      state.dismissAlert();

      state.receiveNotification(
        alarm(_candidate(id: 'cand-2', at: '2026-09-19T20:09:30Z')),
      );

      expect(state.activeAlert?.id, 'cand-2');
    });
  });

  test('abrir la notificación de la alarma sí muestra la pantalla', () async {
    final NotificationService service = NotificationService();
    final List<NotificationEnvelope> received = <NotificationEnvelope>[];
    service.events.listen(received.add);

    service.handleIncomingData(_candidate(), opened: true);
    await pumpEventQueue();

    expect(received.single.critical, isTrue);
  });

  test('un aviso marcado en silencio no es crítico', () async {
    final NotificationService service = NotificationService();
    final List<NotificationEnvelope> received = <NotificationEnvelope>[];
    service.events.listen(received.add);

    service.handleIncomingData(<String, dynamic>{
      ..._candidate(),
      'seismik_quiet': 'true',
    });
    await pumpEventQueue();

    expect(received.single.critical, isFalse);
    expect(received.single.followUp, isTrue);
  });
}
