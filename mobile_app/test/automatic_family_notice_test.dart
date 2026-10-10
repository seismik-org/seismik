import 'package:flutter_test/flutter_test.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:seismik/data/models/family_circle.dart';
import 'package:seismik/services/notification_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  test(
    'Android posts a repeating bounded alarm with a silence action',
    () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      AndroidFlutterLocalNotificationsPlugin.registerWith();
      const MethodChannel channel = MethodChannel(
        'dexterous.com/flutter/local_notifications',
      );
      Map<dynamic, dynamic>? posted;
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(channel, (MethodCall call) async {
            if (call.method == 'show') {
              posted = call.arguments as Map<dynamic, dynamic>;
            }
            return null;
          });
      final NotificationService service = NotificationService();
      try {
        await service.runCriticalAlertTest();
        expect(posted, isNotNull);
        final Map<dynamic, dynamic> android =
            posted!['platformSpecifics'] as Map<dynamic, dynamic>;
        expect(android['channelId'], criticalAlarmChannelId);
        expect(android['additionalFlags'], contains(4));
        expect(android['timeoutAfter'], 60000);
        expect(
          (android['actions'] as List<dynamic>).first['id'],
          'silence-critical',
        );
      } finally {
        await service.dispose();
        debugDefaultTargetPlatformOverride = null;
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(channel, null);
      }
    },
  );
  test('automatic location notice never says a relative is safe', () {
    final FamilyNotification notice = FamilyNotification.fromData(
      <String, dynamic>{'display_name': 'Ana', 'status': 'location_only'},
      opened: false,
    );
    expect(notice.locationOnly, isTrue);
    expect(notice.title, 'Ana: ubicación disponible');
    expect(notice.title.contains('bien'), isFalse);
  });
  test('sharing defaults off and parses only explicit server consent', () {
    expect(
      FamilyCircle.fromMap(<String, dynamic>{}).automaticLocationSharing,
      isFalse,
    );
    expect(
      FamilyCircle.fromMap(<String, dynamic>{
        'automatic_location_sharing': true,
      }).automaticLocationSharing,
      isTrue,
    );
    final FamilyLocation location = FamilyLocation.fromMap(<String, dynamic>{
      'latitude': 4.65,
      'longitude': -74.08,
      'source': 'automatic_alert',
    });
    expect(location.source, 'automatic_alert');
  });
}
