import 'dart:async';
import 'dart:io';
import 'dart:ui';

import 'package:flutter/foundation.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:geolocator/geolocator.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../state/mobile_settings.dart';
import 'accelerometer_service.dart';
import 'api_client.dart';

/// Runs locally on the phone, not in another paid Cloud Run service.
class BackgroundMotionService {
  static final status = ValueNotifier<String>('Segundo plano desactivado');
  static void initialize() {
    if (!Platform.isAndroid) return;
    FlutterForegroundTask.initCommunicationPort();
    FlutterForegroundTask.addTaskDataCallback((data) {
      if (data is String) status.value = data;
    });
    FlutterForegroundTask.init(
      androidNotificationOptions: AndroidNotificationOptions(
        channelId: 'seismik_motion',
        channelName: 'Detección colaborativa',
        channelDescription: 'Sensor voluntario de movimiento en segundo plano',
        onlyAlertOnce: true,
      ),
      iosNotificationOptions: const IOSNotificationOptions(
        showNotification: false,
        playSound: false,
      ),
      foregroundTaskOptions: ForegroundTaskOptions(
        eventAction: ForegroundTaskEventAction.repeat(5000),
        autoRunOnBoot: false,
        autoRunOnMyPackageReplaced: false,
        allowWakeLock: true,
        allowWifiLock: false,
        allowAutoRestart: false,
      ),
    );
  }

  static Future<void> start(ApiClient api, {void Function()? callback}) async {
    if (!Platform.isAndroid) return;
    if (await FlutterForegroundTask.isRunningService) return;
    if (!await api.hasCrowdToken()) {
      throw StateError(
        'Primero registra el dispositivo con conexión a Internet.',
      );
    }
    final permission = await Geolocator.checkPermission();
    if (permission != LocationPermission.whileInUse &&
        permission != LocationPermission.always) {
      throw StateError(
        'Permite la ubicación mientras usas Seismik para activar el sensor.',
      );
    }
    if (!await Geolocator.isLocationServiceEnabled()) {
      throw StateError('Activa la ubicación del teléfono.');
    }
    if (await FlutterForegroundTask.requestNotificationPermission() !=
        NotificationPermission.granted) {
      throw StateError(
        'Permite las notificaciones para disponer del botón Detener.',
      );
    }
    final result = await FlutterForegroundTask.startService(
      serviceId: 731,
      serviceTypes: [
        ForegroundServiceTypes.location,
        ForegroundServiceTypes.specialUse,
      ],
      notificationTitle: 'Seismik · Detección colaborativa',
      notificationText: 'Iniciando sensor voluntario…',
      notificationButtons: [
        const NotificationButton(id: 'stop', text: 'Detener'),
      ],
      callback: callback ?? startBackgroundMotion,
    );
    if (result is ServiceRequestFailure) {
      throw StateError(
        'Android no permitió iniciar el sensor: ${result.error}',
      );
    }
    status.value = 'Iniciando sensor en segundo plano…';
  }

  static Future<void> stop() async {
    if (!Platform.isAndroid) return;
    if (await FlutterForegroundTask.isRunningService) {
      final result = await FlutterForegroundTask.stopService();
      if (result is ServiceRequestFailure) throw StateError('${result.error}');
    }
    status.value = 'Segundo plano desactivado';
  }
}

@pragma('vm:entry-point')
void startBackgroundMotion() {
  DartPluginRegistrant.ensureInitialized();
  FlutterForegroundTask.setTaskHandler(BackgroundMotionTask());
}

class BackgroundMotionTask extends TaskHandler {
  BackgroundMotionTask({ApiClient? apiClient})
    : _api = apiClient ?? ApiClient();
  final ApiClient _api;
  AccelerometerService? _sensor;
  bool _checking = false;
  bool _stopping = false;
  DateTime _startedAt = DateTime.now();
  Position? _lastPosition;
  DateTime _lastNotification = DateTime.fromMillisecondsSinceEpoch(0);

  Future<bool> _consented() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.reload();
    return (prefs.getBool('settings.crowdsourcing') ?? true) &&
        (prefs.getBool(MobileSettings.backgroundCrowdsourcingKey) ?? false);
  }

  @override
  Future<void> onStart(DateTime timestamp, TaskStarter starter) async {
    _startedAt = DateTime.now();
    try {
      if (!await _consented() || !await _api.hasCrowdToken()) {
        await _stop();
        return;
      }
      _sensor = AccelerometerService(
        apiClient: _api,
        locationAccuracyProvider: () => _lastPosition?.accuracy,
        positionProvider: () async {
          if (_stopping || !await _consented()) return null;
          // Reuse a recent fix rather than waking GPS on every candidate peak.
          var position = _lastPosition;
          if (position == null || !usableMotionLocation(position)) {
            position = await Geolocator.getLastKnownPosition();
          }
          if (position == null || !usableMotionLocation(position)) {
            position = await Geolocator.getCurrentPosition(
              locationSettings: const LocationSettings(
                accuracy: LocationAccuracy.medium,
                timeLimit: Duration(seconds: 5),
              ),
            );
          }
          _lastPosition = position;
          if (_stopping ||
              !await _consented() ||
              !usableMotionLocation(position)) {
            return null;
          }
          return (latitude: position.latitude, longitude: position.longitude);
        },
      );
      await _sensor!.start();
      _publish();
    } catch (_) {
      await _stop(
        'No se pudo iniciar el sensor. Revisa los permisos y vuelve a activarlo.',
      );
    }
  }

  @override
  void onRepeatEvent(DateTime timestamp) {
    if (_checking || _stopping) return;
    _checking = true;
    unawaited(() async {
      try {
        final permission = await Geolocator.checkPermission();
        if (!await _consented() ||
            (permission != LocationPermission.whileInUse &&
                permission != LocationPermission.always) ||
            !await Geolocator.isLocationServiceEnabled()) {
          await _stop();
          return;
        }
        final last = _sensor?.lastSampleAt;
        if (DateTime.now().difference(last ?? _startedAt) >
            const Duration(seconds: 30)) {
          await _stop(
            'Android no entrega lecturas; abre Seismik y vuelve a activar el sensor.',
          );
          return;
        }
        await _sensor?.sendShadowPresence();
        _publish();
      } catch (_) {
        await _stop();
      } finally {
        _checking = false;
      }
    }());
  }

  void _publish() {
    final sensor = _sensor;
    if (sensor == null || _stopping) return;
    final text =
        sensor.lastError ??
        'Sensor activo · ${sensor.samplesRead} lecturas · ${sensor.reportsSent} mediciones enviadas';
    FlutterForegroundTask.sendDataToMain(text);
    if (DateTime.now().difference(_lastNotification) >=
        const Duration(seconds: 30)) {
      _lastNotification = DateTime.now();
      unawaited(FlutterForegroundTask.updateService(notificationText: text));
    }
  }

  Future<void> _stop([String reason = 'Segundo plano detenido']) async {
    if (_stopping) return;
    _stopping = true;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool(MobileSettings.backgroundCrowdsourcingKey, false);
    await _sensor?.stop();
    FlutterForegroundTask.sendDataToMain(reason);
    await FlutterForegroundTask.stopService();
  }

  @override
  void onNotificationButtonPressed(String id) {
    if (id == 'stop') unawaited(_stop());
  }

  @override
  Future<void> onDestroy(DateTime timestamp, bool isTimeout) async {
    _stopping = true;
    await _sensor?.stop();
    _api.close();
  }
}

/// Never cluster an old or very imprecise fix as if it were current.
bool usableMotionLocation(Position position, {DateTime? now}) =>
    position.latitude.isFinite &&
    position.longitude.isFinite &&
    position.accuracy.isFinite &&
    position.accuracy >= 0 &&
    position.accuracy <= 500 &&
    (now ?? DateTime.now()).difference(position.timestamp).abs() <=
        const Duration(minutes: 2);
