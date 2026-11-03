import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/family_messages.dart';
import 'package:seismik/data/models/family_circle.dart';
import 'package:seismik/services/service_status.dart';

class _Api extends ApiClient {
  bool offline = true;
  bool legacyResponse = false;
  final List<Map<String, dynamic>> sent = [];
  @override
  Future<void> sendFamilyMessage(Map<String, dynamic> message) async {
    sent.add(Map.of(message));
    if (offline) throw const SeismikApiException('offline', 503);
  }

  @override
  Future<Map<String, dynamic>> fetchFamilyMessages(
    String senderId, {
    String? recipientId,
  }) async => {
    'circle_id': 'circle-1',
    if (!legacyResponse) 'recipient_id': recipientId,
    'messages': <Map<String, dynamic>>[],
  };

  @override
  Future<ConnectionDiagnosis> diagnoseFailure(
    Object? failure, {
    bool hasSignal = true,
  }) async => ConnectionDiagnosis(
    hasSignal ? ConnectionProblem.service : ConnectionProblem.offline,
    'Pendiente de conexión.',
    'Sin conexión',
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));
  FamilyMessages service(_Api api, [String uid = 'owner']) => FamilyMessages(
    api: api,
    uid: uid,
    circleId: 'circle-1',
    senderId: '1234567890abcdef',
  );
  test(
    'network failure survives restart and retry keeps the same identifier',
    () async {
      final api = _Api();
      final first = service(api);
      await first.enqueue('Nos vemos en el parque');
      await first.sync();
      expect(first.pending, hasLength(1));
      final retry = service(api);
      await retry.load();
      expect(
        retry.pending.single['message_id'],
        first.pending.single['message_id'],
      );
      api.offline = false;
      await retry.sync();
      expect(retry.pending, isEmpty);
      expect(api.sent[0]['message_id'], api.sent[1]['message_id']);
    },
  );
  test('another account never loads the previous family outbox', () async {
    final api = _Api();
    final first = service(api);
    await first.enqueue('Privado');
    final other = service(api, 'another');
    await other.load();
    expect(other.pending, isEmpty);
  });
  test(
    'private outboxes stay scoped to recipient, account and circle across restarts',
    () async {
      final api = _Api();
      FamilyMessages direct(String recipient) => FamilyMessages(
        api: api,
        uid: 'owner',
        circleId: 'circle-1',
        senderId: '1234567890abcdef',
        recipientId: recipient,
      );
      final first = direct('aaaaaaaaaaaaaaaa');
      await first.enqueue('Solo para Ana');
      final id = first.pending.single['message_id'];
      final other = direct('bbbbbbbbbbbbbbbb');
      await other.load();
      expect(other.pending, isEmpty);
      final group = service(api);
      await group.load();
      expect(group.pending, isEmpty);
      final restored = direct('aaaaaaaaaaaaaaaa');
      await restored.load();
      expect(restored.pending.single['message_id'], id);
      await restored.sync(hasSignal: false);
      expect(api.sent, isEmpty);
      api.offline = false;
      await restored.sync();
      expect(api.sent.single['recipient_id'], 'aaaaaaaaaaaaaaaa');
      expect(api.sent.single['message_id'], id);
      expect(restored.pending, isEmpty);
    },
  );
  test(
    'older server responses cannot populate a private conversation with group messages',
    () async {
      final api = _Api()..legacyResponse = true;
      final direct = FamilyMessages(
        api: api,
        uid: 'owner',
        circleId: 'circle-1',
        senderId: '1234567890abcdef',
        recipientId: 'aaaaaaaaaaaaaaaa',
      );
      await direct.sync();
      expect(direct.received, isEmpty);
      expect(direct.notice, contains('No se pudo verificar el chat privado'));
    },
  );
  test(
    'expired messages remain for review and are never transmitted',
    () async {
      final api = _Api()..offline = false;
      final messages = service(api);
      await messages.enqueue(
        'Aviso antiguo',
        now: DateTime.now().subtract(const Duration(hours: 25)),
      );
      await messages.sync();
      expect(api.sent, isEmpty);
      expect(messages.pending, hasLength(1));
      await messages.cancel(messages.pending.single['message_id'] as String);
      expect(messages.pending, isEmpty);
    },
  );
  test('blank and oversize messages never enter the outbox', () async {
    final messages = service(_Api());
    await expectLater(messages.enqueue(' '), throwsArgumentError);
    await expectLater(messages.enqueue('x' * 281), throwsArgumentError);
    expect(messages.pending, isEmpty);
  });
  test(
    'offline membership never revives a cached safety status or location',
    () async {
      final circle = FamilyCircle.fromMap({
        'circle_id': 'circle-1',
        'circle_name': 'Familia',
        'is_owner': true,
        'members': [
          {
            'member_id': '1234567890abcdef',
            'display_name': 'Ana',
            'is_you': true,
            'is_owner': true,
            'location': {
              'latitude': 4.6,
              'longitude': -74.0,
              'precision': 'approximate',
              'expires_at': '2026-01-01T00:00:00Z',
            },
            'status': {'status': 'safe', 'reported_at': '2026-01-01T00:00:00Z'},
          },
        ],
      });
      await FamilyCircleCache.save('owner', circle);
      final cached = await FamilyCircleCache.load('owner');
      expect(cached?.you?.displayName, 'Ana');
      expect(cached?.you?.location, isNull);
      expect(cached?.you?.status, isNull);
      expect(await FamilyCircleCache.load('another'), isNull);
    },
  );
}
