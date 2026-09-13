import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/services/account_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const MethodChannel channel = MethodChannel(OAuthBrowserFlow.channelName);

  test('el challenge coincide con el vector del RFC 7636', () {
    expect(
      PkcePair.challengeFor('dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk'),
      'E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM',
    );
  });

  test('cada inicio de sesión usa un verificador nuevo y válido', () {
    final PkcePair first = PkcePair.generate();
    final PkcePair second = PkcePair.generate();

    expect(first.verifier, isNot(second.verifier));
    expect(first.verifier, matches(RegExp(r'^[A-Za-z0-9_-]{43,128}$')));
    expect(first.challenge, PkcePair.challengeFor(first.verifier));
  });

  test('el retorno nativo completa el inicio de sesión', () async {
    String? pending;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (MethodCall call) async {
          if (call.method != 'takePendingCallback') return null;
          final String? value = pending;
          pending = null;
          return value;
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, null),
    );
    Uri? opened;
    final OAuthBrowserFlow flow = OAuthBrowserFlow(
      channel: channel,
      launcher: (Uri uri) async {
        opened = uri;
        return true;
      },
    );
    addTearDown(flow.dispose);

    final Future<Uri> result = flow.authorize(
      provider: 'google',
      challenge: 'c' * 43,
    );
    await pumpEventQueue();
    expect(opened!.host, 'auth.seismik.org');
    expect(opened!.path, '/v1/oauth/authorize');
    expect(opened!.queryParameters['origin'], 'app');
    expect(opened!.queryParameters['app_challenge'], 'c' * 43);

    // Android entrega el retorno y avisa a Dart de que ya está disponible.
    pending = 'seismik://auth/callback?code=codigo-123';
    await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .handlePlatformMessage(
          OAuthBrowserFlow.channelName,
          const StandardMethodCodec().encodeMethodCall(
            const MethodCall('callbackAvailable'),
          ),
          (_) {},
        );

    expect((await result).queryParameters['code'], 'codigo-123');
  });

  test('si el navegador no abre, el inicio de sesión se cancela', () async {
    final OAuthBrowserFlow flow = OAuthBrowserFlow(
      channel: channel,
      launcher: (_) async => false,
    );
    addTearDown(flow.dispose);

    await expectLater(
      flow.authorize(provider: 'google', challenge: 'c' * 43),
      throwsA(isA<SignInCancelled>()),
    );
  });
}
