// DEBUG-ONLY isolated package. No Firebase session and no production requests.
// flutter build apk --debug -t tool/background_motion_probe.dart -PseismikMotionProbe=true
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:seismik/services/api_client.dart';
import 'package:seismik/services/background_motion_service.dart';
import 'package:seismik/state/mobile_settings.dart';

class DryRunApi extends ApiClient {
  @override
  Future<bool> hasCrowdToken() async => true;
  @override
  Future<void> sendShake({
    required double latitude,
    required double longitude,
    required double pgaG,
    required int timestampMilliseconds,
  }) async {
    debugPrint('SEISMIK_PROBE dry-run summary accepted; NO network request');
  }
}

@pragma('vm:entry-point')
void probeCallback() {
  DartPluginRegistrant.ensureInitialized();
  FlutterForegroundTask.setTaskHandler(
    BackgroundMotionTask(apiClient: DryRunApi()),
  );
}

void main() {
  if (!kDebugMode) throw StateError('The sensor probe is debug-only.');
  WidgetsFlutterBinding.ensureInitialized();
  BackgroundMotionService.initialize();
  BackgroundMotionService.status.addListener(() {
    debugPrint('SEISMIK_PROBE ${BackgroundMotionService.status.value}');
  });
  runApp(
    MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Seismik · prueba local')),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Prueba del sensor real. SIN envíos a producción.'),
              ValueListenableBuilder(
                valueListenable: BackgroundMotionService.status,
                builder: (context, value, _) => Text(value),
              ),
              FilledButton(
                onPressed: () async {
                  try {
                    await Geolocator.requestPermission();
                    final prefs = await SharedPreferences.getInstance();
                    await prefs.setBool('settings.crowdsourcing', true);
                    await prefs.setBool(
                      MobileSettings.backgroundCrowdsourcingKey,
                      true,
                    );
                    final api = DryRunApi();
                    try {
                      await BackgroundMotionService.start(
                        api,
                        callback: probeCallback,
                      );
                    } finally {
                      api.close();
                    }
                  } catch (error) {
                    BackgroundMotionService.status.value = '$error';
                  }
                },
                child: const Text('Iniciar prueba'),
              ),
              TextButton(
                onPressed: () async {
                  final prefs = await SharedPreferences.getInstance();
                  await prefs.setBool(
                    MobileSettings.backgroundCrowdsourcingKey,
                    false,
                  );
                  await BackgroundMotionService.stop();
                },
                child: const Text('Detener'),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}
