import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/family_messages.dart';
import 'package:seismik/data/models/family_circle.dart';

class _Api extends ApiClient {
  bool offline = true;
  final List<Map<String, dynamic>> sent = [];
  @override
  Future<void> sendFamilyMessage(Map<String, dynamic> message) async {
    sent.add(Map.of(message));
    if (offline) throw const SeismikApiException('offline', 503);
  }

  @override
  Future<Map<String, dynamic>> fetchFamilyMessages(String senderId) async => {
    'circle_id': 'circle-1',
    'messages': <Map<String, dynamic>>[],
  };
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
