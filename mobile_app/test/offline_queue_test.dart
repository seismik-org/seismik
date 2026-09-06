import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/pending_report.dart';
import 'package:seismik/services/offline_queue.dart';
import 'package:shared_preferences/shared_preferences.dart';

PendingReport report(
  String id, {
  PendingReportKind kind = PendingReportKind.felt,
  DateTime? queuedAt,
  int attempts = 0,
}) => PendingReport(
  reportId: id,
  kind: kind,
  payload: <String, dynamic>{'report_id': id, 'type': 'seismik_felt_report'},
  queuedAt: queuedAt ?? DateTime.now().toUtc(),
  attempts: attempts,
);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues(<String, Object>{}));

  test('un reporte encolado sobrevive al reinicio de la app', () async {
    const OfflineReportQueue queue = OfflineReportQueue();
    await queue.enqueue(report('report-1'));

    const OfflineReportQueue restarted = OfflineReportQueue();
    final List<PendingReport> pending = await restarted.load();
    expect(pending, hasLength(1));
    expect(pending.single.reportId, 'report-1');
    expect(pending.single.payload['type'], 'seismik_felt_report');
  });

  test('reencolar el mismo report_id no lo duplica', () async {
    const OfflineReportQueue queue = OfflineReportQueue();
    await queue.enqueue(report('report-1'));
    await queue.enqueue(report('report-1'));

    expect(await queue.pendingCount(), 1);
  });

  test('la cola conserva los reportes más recientes al llenarse', () async {
    const OfflineReportQueue queue = OfflineReportQueue(maxEntries: 2);
    for (final String id in <String>['a', 'b', 'c']) {
      await queue.enqueue(report(id));
    }

    final List<PendingReport> pending = await queue.load();
    expect(pending.map((item) => item.reportId), <String>['b', 'c']);
  });

  test('al volver la red se envían en orden y la cola queda vacía', () async {
    const OfflineReportQueue queue = OfflineReportQueue();
    await queue.enqueue(report('a'));
    await queue.enqueue(report('b', kind: PendingReportKind.damage));

    final List<String> sent = <String>[];
    final QueueFlushResult result = await queue.flush((item) async {
      sent.add('${item.kind.id}:${item.reportId}');
    });

    expect(sent, <String>['felt:a', 'damage:b']);
    expect(result.sent, 2);
    expect(result.remaining, 0);
    expect(await queue.pendingCount(), 0);
  });

  test('un fallo de red detiene el envío y conserva el resto', () async {
    const OfflineReportQueue queue = OfflineReportQueue();
    await queue.enqueue(report('a'));
    await queue.enqueue(report('b'));
    await queue.enqueue(report('c'));

    int calls = 0;
    final QueueFlushResult result = await queue.flush((item) async {
      calls++;
      if (item.reportId != 'a') throw Exception('sin conexión');
    });

    expect(calls, 2);
    expect(result.sent, 1);
    expect(result.remaining, 2);
    final List<PendingReport> pending = await queue.load();
    expect(pending.map((item) => item.reportId), <String>['b', 'c']);
    expect(pending.first.attempts, 1);
    expect(pending.first.lastError, contains('sin conexión'));
  });

  test('un rechazo definitivo del servidor no se reintenta', () async {
    const OfflineReportQueue queue = OfflineReportQueue();
    await queue.enqueue(report('a'));
    await queue.enqueue(report('b'));

    final QueueFlushResult result = await queue.flush((item) async {
      if (item.reportId == 'a') {
        throw const PermanentReportRejection('cuerpo inválido');
      }
    });

    expect(result.discarded, 1);
    expect(result.sent, 1);
    expect(await queue.pendingCount(), 0);
  });

  test('un reporte demasiado antiguo se descarta sin enviarse', () async {
    const OfflineReportQueue queue = OfflineReportQueue(
      maxAge: Duration(days: 30),
    );
    await queue.enqueue(
      report(
        'viejo',
        queuedAt: DateTime.now().toUtc().subtract(const Duration(days: 31)),
      ),
    );

    int calls = 0;
    final QueueFlushResult result = await queue.flush((_) async => calls++);

    expect(calls, 0);
    expect(result.discarded, 1);
    expect(await queue.pendingCount(), 0);
  });

test('un reporte que agota los reintentos permanece disponible para reintento manual', () async {
    const OfflineReportQueue queue = OfflineReportQueue(maxAttempts: 3);
    await queue.enqueue(report('a', attempts: 2));

    final QueueFlushResult result = await queue.flush((_) async {
      throw Exception('sin conexión');
    });

  expect(result.discarded, 0);
  expect(await queue.pendingCount(), 1);
  });

  test('una entrada corrupta se ignora sin bloquear las demás', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{
      'seismik.pending_reports': <String>['{ truncado', report('ok').encode()],
    });
    const OfflineReportQueue queue = OfflineReportQueue();

    final List<PendingReport> pending = await queue.load();
    expect(pending, hasLength(1));
    expect(pending.single.reportId, 'ok');
  });

  test('vaciar una cola vacía no falla', () async {
    const OfflineReportQueue queue = OfflineReportQueue();
    final QueueFlushResult result = await queue.flush((_) async {});
    expect(result.sent, 0);
    expect(result.remaining, 0);
  });

  test('el reporte codificado conserva el cuerpo original', () {
    final PendingReport original = report('a', kind: PendingReportKind.damage);
    final PendingReport decoded = PendingReport.tryDecode(original.encode())!;

    expect(decoded.reportId, original.reportId);
    expect(decoded.kind, PendingReportKind.damage);
    expect(decoded.kind.path, '/v1/reports/damage');
    expect(decoded.payload, original.payload);
  });
}
