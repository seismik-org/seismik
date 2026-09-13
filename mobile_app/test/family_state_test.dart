import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/data/models/family_circle.dart';
import 'package:seismik/data/models/seismic_event.dart';
import 'package:seismik/data/models/seismik_account.dart';
import 'package:seismik/services/account_service.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/notification_service.dart';
import 'package:seismik/state/family_state.dart';
import 'package:seismik/state/mobile_settings.dart';
import 'package:seismik/state/seismik_state.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _FakeAuthorizer implements OAuthAuthorizer {
  _FakeAuthorizer({this.cancel = false});

  final bool cancel;
  String? challenge;

  @override
  Future<Uri> authorize({
    required String provider,
    required String challenge,
  }) async {
    this.challenge = challenge;
    if (cancel) throw const SignInCancelled();
    return Uri.parse('seismik://auth/callback?code=codigo-1');
  }

  @override
  void dispose() {}
}

class _FamilyApi extends ApiClient {
  SeismikAccount? account;
  String? verifier;
  int links = 0;
  bool expired = false;
  FamilyCircle? circle;
  final List<String?> reportedEvents = <String?>[];

  @override
  Future<SeismikAccount?> currentAccount() async => account;

  @override
  Future<SeismikAccount> exchangeOAuthCode({
    required String code,
    required String verifier,
  }) async {
    this.verifier = verifier;
    return account = const SeismikAccount(
      uid: 'google-1',
      email: 'ana@example.test',
      name: 'Ana',
    );
  }

  @override
  Future<void> clearAccount() async => account = null;

  @override
  Future<void> linkDeviceToAccount() async => links++;

  @override
  Future<FamilyCircle?> fetchFamilyCircle() async {
    if (expired) throw const SeismikApiException('Account session expired', 401);
    return circle;
  }

  @override
  Future<void> reportFamilyStatus({
    required bool needsHelp,
    String? message,
    String? eventId,
    double? latitude,
    double? longitude,
    bool precise = false,
    int shareMinutes = 240,
  }) async => reportedEvents.add(eventId);
}

FamilyCircle circleNamed(String name) => FamilyCircle.fromMap(<String, dynamic>{
  'circle_id': 'c',
  'circle_name': name,
  'is_owner': true,
  'members': <dynamic>[],
});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late MobileSettings settings;

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    settings = MobileSettings();
    await settings.load();
  });

  FamilyState familyWith(_FamilyApi api, _FakeAuthorizer authorizer) =>
      FamilyState(
        seismik: SeismikState(settings: settings, apiClient: api),
        authorizer: authorizer,
      );

  test('iniciar sesión canjea el código con el verificador de su challenge', () async {
    final _FamilyApi api = _FamilyApi()..circle = circleNamed('Casa');
    final _FakeAuthorizer authorizer = _FakeAuthorizer();
    final FamilyState family = familyWith(api, authorizer);

    await family.signIn();

    expect(PkcePair.challengeFor(api.verifier!), authorizer.challenge);
    expect(family.account?.email, 'ana@example.test');
    expect(api.links, 1, reason: 'el teléfono queda asociado para recibir avisos');
    expect(family.circle?.circleName, 'Casa');
    expect(family.signingIn, isFalse);
    expect(family.error, isNull);
  });

  test('cerrar la ventana de Google no muestra un error', () async {
    final FamilyState family = familyWith(
      _FamilyApi(),
      _FakeAuthorizer(cancel: true),
    );

    await family.signIn();

    expect(family.account, isNull);
    expect(family.error, isNull);
    expect(family.signingIn, isFalse);
  });

  test('una sesión vencida vuelve a pedir inicio de sesión', () async {
    final _FamilyApi api = _FamilyApi()
      ..account = const SeismikAccount(uid: 'u', email: 'e@x.test', name: 'E')
      ..expired = true;
    final FamilyState family = familyWith(api, _FakeAuthorizer());

    await family.initialize();

    expect(family.account, isNull);
    expect(family.error, contains('venció'));
  });

  test('avisar desde la alerta abre Familia y liga el aviso al sismo', () async {
    final _FamilyApi api = _FamilyApi()
      ..account = const SeismikAccount(uid: 'u', email: 'e@x.test', name: 'E')
      ..circle = circleNamed('Casa');
    final FamilyState family = familyWith(api, _FakeAuthorizer());
    final SeismicEvent event = SeismicEvent.fromMap(<String, dynamic>{
      'event_id': 'official-sgc-1',
      'type': 'official_report_update',
      'origin_time': '2026-09-12T20:00:00Z',
    });
    int openRequests = 0;
    family.openRequests.addListener(() => openRequests++);

    family.requestCheckIn(event);
    expect(openRequests, 1);
    expect(family.checkInEvent?.id, 'official-sgc-1');

    await family.reportStatus(needsHelp: false);

    expect(api.reportedEvents, <String?>['official-sgc-1']);
    expect(family.checkInEvent, isNull);
    expect(family.reporting, isFalse);
  });

  test('un aviso familiar abierto lleva a la pestaña Familia', () async {
    final _FamilyApi api = _FamilyApi()
      ..account = const SeismikAccount(uid: 'u', email: 'e@x.test', name: 'E');
    final SeismikState seismik = SeismikState(settings: settings, apiClient: api);
    final FamilyState family = FamilyState(
      seismik: seismik,
      authorizer: _FakeAuthorizer(),
    );
    int openRequests = 0;
    family.openRequests.addListener(() => openRequests++);

    seismik.notifications.handleIncomingData(<String, dynamic>{
      'type': FamilyNotification.type,
      'event_id': 'family-1',
      'display_name': 'Luis',
      'status': 'safe',
    }, opened: true);
    await pumpEventQueue();

    expect(openRequests, 1);
    expect(seismik.recentEvents, isEmpty, reason: 'no es un sismo');
  });
}
