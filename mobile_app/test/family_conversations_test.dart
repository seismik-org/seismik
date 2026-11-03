import 'dart:io';
import 'dart:ui' as ui;
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:seismik/core/theme.dart';
import 'package:seismik/data/models/family_circle.dart';
import 'package:seismik/presentation/widgets/family_messages_card.dart';
import 'package:seismik/services/api_client.dart';

class ChatApi extends ApiClient {
  final sent = <Map<String, dynamic>>[];
  @override
  Future<Map<String, dynamic>> fetchFamilyMessages(
    String senderId, {
    String? recipientId,
  }) async => {
    'circle_id': 'test-circle-1',
    'recipient_id': recipientId,
    'messages': [
      {
        'sender_id': 'aaaaaaaaaaaaaaaa',
        'recipient_id': recipientId == null ? null : senderId,
        'display_name': 'Ana',
        'text': recipientId == null ? 'Hola grupo' : 'Hola en privado',
        'expires_at': DateTime.now()
            .add(const Duration(hours: 24))
            .toUtc()
            .toIso8601String(),
      },
    ],
  };
  @override
  Future<void> sendFamilyMessage(Map<String, dynamic> message) async {
    sent.add(Map.of(message));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() => FlutterSecureStorage.setMockInitialValues({}));
  testWidgets(
    'family and private composer switch without leaking or retargeting messages',
    (tester) async {
      const output = String.fromEnvironment('SEISMIK_REVIEW_OUTPUT');
      const fontPath = String.fromEnvironment('SEISMIK_REVIEW_FONT');
      const iconPath = String.fromEnvironment('SEISMIK_REVIEW_ICONS');
      const darkPreview = bool.fromEnvironment('SEISMIK_REVIEW_DARK');
      if (output.isNotEmpty) {
        tester.view.physicalSize = const Size(432, 850);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        if (fontPath.isNotEmpty) {
          await tester.runAsync(() async {
            final data = await File(fontPath).readAsBytes();
            await (FontLoader(
              'Roboto',
            )..addFont(Future.value(ByteData.sublistView(data)))).load();
          });
        }
      }
      if (output.isNotEmpty && iconPath.isNotEmpty) {
        await tester.runAsync(() async {
          final data = await File(iconPath).readAsBytes();
          await (FontLoader(
            'MaterialIcons',
          )..addFont(Future.value(ByteData.sublistView(data)))).load();
        });
      }
      Future<void> capture(String name) async {
        if (output.isEmpty) return;
        await tester.runAsync(() async {
          final boundary = tester.firstRenderObject<RenderRepaintBoundary>(
            find.byKey(const ValueKey('review-capture')),
          );
          final image = await boundary.toImage(pixelRatio: 2);
          final data = await image.toByteData(format: ui.ImageByteFormat.png);
          await File(
            '$output/$name.png',
          ).writeAsBytes(data!.buffer.asUint8List());
          image.dispose();
        });
      }

      final api = ChatApi();
      final members = [
        FamilyMember.fromMap({
          'member_id': '1234567890abcdef',
          'display_name': 'Tú',
          'is_you': true,
        }),
        FamilyMember.fromMap({
          'member_id': 'aaaaaaaaaaaaaaaa',
          'display_name': 'Ana',
        }),
      ];
      await tester.pumpWidget(
        MaterialApp(
          theme: SeismikTheme.fromScheme(
            SeismikTheme.scheme(
              brightness: darkPreview ? Brightness.dark : Brightness.light,
            ),
          ),
          home: RepaintBoundary(
            key: const ValueKey('review-capture'),
            child: Scaffold(
              body: SingleChildScrollView(
                child: FamilyConversationsCard(
                  api: api,
                  uid: 'test-account',
                  circleId: 'test-circle-1',
                  senderId: '1234567890abcdef',
                  members: members,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Hola grupo'), findsOneWidget);
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Privado · Ana').last);
      await tester.pumpAndSettle();
      expect(find.text('Hola grupo'), findsNothing);
      expect(find.text('Hola en privado'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await capture(
        darkPreview ? 'familia-privado-oscuro' : 'familia-privado-claro',
      );
      await tester.enterText(find.byType(TextField), 'Te espero aquí');
      await tester.ensureVisible(find.text('Enviar'));
      await tester.tap(find.text('Enviar'));
      await tester.pumpAndSettle();
      expect(api.sent.single['recipient_id'], 'aaaaaaaaaaaaaaaa');
      expect(api.sent.single['text'], 'Te espero aquí');
      await tester.ensureVisible(find.byType(DropdownButtonFormField<String>));
      await tester.tap(find.byType(DropdownButtonFormField<String>));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Todo el círculo familiar').last);
      await tester.pumpAndSettle();
      expect(find.text('Hola en privado'), findsNothing);
      expect(find.text('Hola grupo'), findsOneWidget);
      expect(api.sent, hasLength(1));
      await tester.pumpWidget(const SizedBox.shrink());
      api.close();
    },
  );
}
