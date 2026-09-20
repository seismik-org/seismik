import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:seismik_wear/family.dart';
import 'package:seismik_wear/family_screen.dart';

/// Familia en el reloj se apoya en la sesión que publica el teléfono. Estas
/// pruebas fijan lo que viaja al servidor y lo que ve la persona cuando no hay
/// sesión, que es el caso más probable la primera vez.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const MethodChannel channel = MethodChannel('seismik/wear');

  /// Simula el puente nativo: `null` es un teléfono sin sesión iniciada.
  void shareSession(String? session) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (MethodCall call) async {
          expect(call.method, 'accountSession');
          return session == null
              ? null
              : <Object?, Object?>{'session': session, 'name': 'Ana'};
        });
  }

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  });

  test('el aviso viaja con la sesión del teléfono y el sismo', () async {
    shareSession('sesion-del-telefono');
    http.Request? sent;
    final WearFamily family = WearFamily(
      channel: channel,
      client: MockClient((http.Request request) async {
        sent = request;
        return http.Response('{"status":"safe"}', 200);
      }),
    );

    await family.report(needsHelp: false, eventId: 'sgc_colombia:SGC2026abc');

    expect(sent!.method, 'PUT');
    expect(sent!.url.path, '/v1/family/status');
    expect(sent!.headers['X-Seismik-Account-Session'], 'sesion-del-telefono');
    final Map<String, dynamic> body =
        jsonDecode(sent!.body) as Map<String, dynamic>;
    expect(body['status'], 'safe');
    expect(body['event_id'], 'sgc_colombia:SGC2026abc');
    expect(
      body.containsKey('location'),
      isFalse,
      reason: 'la ubicación la comparte el teléfono, no el reloj',
    );
  });

  test('«necesito ayuda» se envía como tal', () async {
    shareSession('sesion');
    late Map<String, dynamic> body;
    final WearFamily family = WearFamily(
      channel: channel,
      client: MockClient((http.Request request) async {
        body = jsonDecode(request.body) as Map<String, dynamic>;
        return http.Response('{}', 200);
      }),
    );

    await family.report(needsHelp: true);

    expect(body['status'], 'need_help');
  });

  test('sin sesión del teléfono no se inventa nada', () async {
    shareSession(null);
    final WearFamily family = WearFamily(
      channel: channel,
      client: MockClient((http.Request request) async {
        fail('no debe llamar al servidor sin sesión');
      }),
    );

    expect(await family.session(), isNull);
    expect(
      () => family.report(needsHelp: false),
      throwsA(isA<Exception>()),
    );
  });

  test('una sesión caducada se explica en vez de reintentar en silencio', () async {
    shareSession('caducada');
    final WearFamily family = WearFamily(
      channel: channel,
      client: MockClient(
        (http.Request request) async => http.Response('{}', 401),
      ),
    );

    await expectLater(
      family.report(needsHelp: false),
      throwsA(
        predicate(
          (Object? error) => '$error'.contains('caducó'),
          'menciona que la sesión caducó',
        ),
      ),
    );
  });

  test('el círculo llega con el estado de cada quien', () async {
    shareSession('sesion');
    final WearFamily family = WearFamily(
      channel: channel,
      client: MockClient(
        (http.Request request) async => http.Response(
          jsonEncode(<String, dynamic>{
            'circle_name': 'Casa',
            'members': <Map<String, dynamic>>[
              <String, dynamic>{
                'display_name': 'Ana',
                'is_you': true,
                'status': <String, dynamic>{
                  'status': 'safe',
                  'reported_at': '2026-09-20T15:00:00Z',
                },
              },
              <String, dynamic>{'display_name': 'Jorge', 'is_you': false},
            ],
          }),
          200,
        ),
      ),
    );

    final FamilyCircle? circle = await family.circle();

    expect(circle!.name, 'Casa');
    expect(circle.members.first.isYou, isTrue);
    expect(circle.members.first.statusLabel, 'Está bien');
    expect(circle.members.last.statusLabel, 'Sin aviso');
  });

  testWidgets('sin sesión, la pantalla dice qué hacer y cabe en el reloj', (
    WidgetTester tester,
  ) async {
    shareSession(null);
    tester.view.physicalSize = const Size(426, 426);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        home: FamilyScreen(
          family: WearFamily(
            channel: channel,
            client: MockClient(
              (http.Request request) async => http.Response('{}', 200),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('Inicia sesión en Seismik'), findsOneWidget);
    expect(find.text('Estoy bien'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets('con sesión aparecen los dos botones de aviso', (
    WidgetTester tester,
  ) async {
    shareSession('sesion');
    tester.view.physicalSize = const Size(426, 426);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);

    await tester.pumpWidget(
      MaterialApp(
        home: FamilyScreen(
          family: WearFamily(
            channel: channel,
            client: MockClient(
              (http.Request request) async => http.Response(
                jsonEncode(<String, dynamic>{
                  'circle_name': 'Casa',
                  'members': <Map<String, dynamic>>[],
                }),
                200,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('Estoy bien'), findsOneWidget);
    expect(find.text('Necesito ayuda'), findsOneWidget);
    expect(find.text('Casa'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
