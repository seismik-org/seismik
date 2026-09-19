import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import '../core/constants.dart';
import '../data/models/seismic_event.dart';
import 'alert_memory.dart';

/// Marca de los avisos que llegaron en silencio porque su sismo ya sonó:
/// abrirlos no vuelve a mostrar la pantalla de alarma.
const String _quietKey = 'seismik_quiet';

const AndroidNotificationChannel _criticalChannel = AndroidNotificationChannel(
  SeismikConstants.criticalChannelId,
  'Alertas sísmicas críticas',
  description: 'Alertas inmediatas de detección sísmica Seismik.',
  importance: Importance.max,
  playSound: true,
  sound: RawResourceAndroidNotificationSound('alarm'),
  audioAttributesUsage: AudioAttributesUsage.alarm,
  enableVibration: true,
  showBadge: true,
);

const AndroidNotificationChannel _updatesChannel = AndroidNotificationChannel(
  SeismikConstants.updatesChannelId,
  'Reportes sísmicos oficiales',
  description: 'Actualizaciones verificadas de servicios geológicos.',
  importance: Importance.defaultImportance,
);

final FlutterLocalNotificationsPlugin _backgroundNotifications =
    FlutterLocalNotificationsPlugin();

@pragma('vm:entry-point')
Future<void> seismikFirebaseBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  await _initializeLocalPlugin(_backgroundNotifications);
  if (_isCritical(message.data)) {
    await _presentCritical(
      _backgroundNotifications,
      message.data,
      AlertMemory(),
    );
  }
}

class NotificationEnvelope {
  const NotificationEnvelope({
    required this.event,
    required this.critical,
    this.followUp = false,
  });
  final SeismicEvent event;
  final bool critical;

  /// Otro aviso de un sismo que ya sonó: trae datos nuevos pero no suena.
  final bool followUp;
}

/// Aviso de que un familiar reportó su estado tras un sismo.
class FamilyNotification {
  const FamilyNotification({
    required this.displayName,
    required this.needsHelp,
    required this.opened,
  });

  factory FamilyNotification.fromData(
    Map<String, dynamic> data, {
    required bool opened,
  }) => FamilyNotification(
    displayName: (data['display_name'] ?? 'Tu familiar').toString(),
    needsHelp: data['status']?.toString() == 'need_help',
    opened: opened,
  );

  static const String type = 'family_status';

  final String displayName;
  final bool needsHelp;

  /// La persona tocó el aviso: hay que llevarla a la pestaña Familia.
  final bool opened;

  String get title =>
      needsHelp ? '$displayName necesita ayuda' : '$displayName está bien';
}

class NotificationService {
  NotificationService({AlertMemory? memory}) : _memory = memory ?? AlertMemory();

  final AlertMemory _memory;
  final FlutterLocalNotificationsPlugin _local =
      FlutterLocalNotificationsPlugin();
  final StreamController<NotificationEnvelope> _events =
      StreamController<NotificationEnvelope>.broadcast();
  final StreamController<FamilyNotification> _family =
      StreamController<FamilyNotification>.broadcast();
  final List<StreamSubscription<RemoteMessage>> _subscriptions =
      <StreamSubscription<RemoteMessage>>[];

  Stream<NotificationEnvelope> get events => _events.stream;

  Stream<FamilyNotification> get familyUpdates => _family.stream;

  Future<void> initialize() async {
    if (Firebase.apps.isEmpty) await Firebase.initializeApp();
    try {
      await FirebaseAppCheck.instance.activate(
        providerAndroid: kReleaseMode
            ? const AndroidPlayIntegrityProvider()
            : const AndroidDebugProvider(),
        providerApple: kReleaseMode
            ? const AppleAppAttestWithDeviceCheckFallbackProvider()
            : const AppleDebugProvider(),
      );
    } catch (_) {
      if (SeismikConstants.integrityRequired) rethrow;
    }
    FirebaseMessaging.onBackgroundMessage(seismikFirebaseBackgroundHandler);
    await _initializeLocalPlugin(
      _local,
      onResponse: (NotificationResponse response) {
        _emitPayload(response.payload);
      },
    );
    // A full-screen intent behaves like a notification tap. When Android had
    // to start a terminated Flutter process, the callback above did not exist
    // yet, so the launch payload must be recovered explicitly.
    final NotificationAppLaunchDetails? launchDetails = await _local
        .getNotificationAppLaunchDetails();
    if (launchDetails?.didNotificationLaunchApp ?? false) {
      _emitPayload(launchDetails?.notificationResponse?.payload);
    }
    await _requestPermissions();
    _subscriptions.add(
      FirebaseMessaging.onMessage.listen((RemoteMessage message) async {
        final Map<String, dynamic> data = Map<String, dynamic>.from(
          message.data,
        );
        if (_isCritical(data)) {
          final bool rang = await _presentCritical(_local, data, _memory);
          _emit(data, critical: rang, followUp: !rang);
          return;
        }
        if (_isFamily(data)) {
          // Con la app abierta Android no muestra el aviso por su cuenta.
          await _showFamilyNotification(_local, message);
        }
        _emit(data);
      }),
    );
    _subscriptions.add(
      FirebaseMessaging.onMessageOpenedApp.listen(
        (RemoteMessage message) =>
            _emit(Map<String, dynamic>.from(message.data), opened: true),
      ),
    );
    final RemoteMessage? initial = await FirebaseMessaging.instance
        .getInitialMessage();
    if (initial != null) {
      _emit(Map<String, dynamic>.from(initial.data), opened: true);
    }
  }

  Future<void> _requestPermissions() async {
    await FirebaseMessaging.instance.requestPermission(
      alert: true,
      badge: true,
      sound: true,
      criticalAlert: true,
      provisional: false,
    );
    if (Platform.isAndroid) {
      final AndroidFlutterLocalNotificationsPlugin? android = _local
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >();
      await android?.requestNotificationsPermission();
    } else if (Platform.isIOS) {
      await _local
          .resolvePlatformSpecificImplementation<
            IOSFlutterLocalNotificationsPlugin
          >()
          ?.requestPermissions(
            alert: true,
            badge: true,
            sound: true,
            critical: true,
          );
    }
  }

  /// Opens Android's dedicated full-screen alert access page when needed.
  /// Android 14+ may otherwise downgrade an alarm to a heads-up banner.
  Future<bool> requestCriticalAlertAccess() async {
    if (!Platform.isAndroid) return true;
    final AndroidFlutterLocalNotificationsPlugin? android = _local
        .resolvePlatformSpecificImplementation<
          AndroidFlutterLocalNotificationsPlugin
        >();
    await android?.requestNotificationsPermission();
    return await android?.requestFullScreenIntentPermission() ?? false;
  }

  Future<void> runCriticalAlertTest() async {
    final Map<String, dynamic> data = <String, dynamic>{
      'type': 'earthquake_candidate',
      'event_id':
          'local-critical-test-${DateTime.now().millisecondsSinceEpoch}',
      'zone_id': 'local-test',
      'detected_at': DateTime.now().toUtc().toIso8601String(),
      'critical': 'true',
      'channel_id': SeismikConstants.criticalChannelId,
    };
    // La prueba siempre suena y no se anota: no puede silenciar un sismo real.
    await _showCriticalNotification(_local, data);
    _emit(data);
  }

  /// Apaga la alarma al cerrar la pantalla roja. La notificación crítica es
  /// fija (no se puede deslizar) y seguía en la barra, lista para sonar otra
  /// vez; ocultar sólo la pantalla dejaba la alarma encendida.
  Future<void> dismissCriticalAlerts() async {
    try {
      final List<ActiveNotification> active = await _local
          .getActiveNotifications();
      for (final ActiveNotification notification in active) {
        final int? id = notification.id;
        if (id != null &&
            notification.channelId == SeismikConstants.criticalChannelId) {
          await _local.cancel(id: id, tag: notification.tag);
        }
      }
    } catch (_) {
      // Sin plugin (pruebas) o sin permiso de notificaciones no hay nada que
      // apagar; cerrar la pantalla no puede fallar por esto.
    }
  }

  void _emitPayload(String? payload) {
    if (payload == null || payload.isEmpty) return;
    try {
      final Object? decoded = jsonDecode(payload);
      if (decoded is Map<String, dynamic>) _emit(decoded, opened: true);
    } on FormatException {
      // Ignore notifications not created by Seismik.
    }
  }

  /// Punto de entrada de los datos de un aviso, expuesto para las pruebas.
  @visibleForTesting
  void handleIncomingData(Map<String, dynamic> data, {bool opened = false}) =>
      _emit(data, opened: opened);

  void _emit(
    Map<String, dynamic> data, {
    bool opened = false,
    bool? critical,
    bool followUp = false,
  }) {
    final String type = (data['type'] ?? '').toString();
    if (type.isEmpty) return;
    // Un aviso familiar no es un sismo: convertirlo en SeismicEvent lo metía
    // en el historial y en el mapa como un evento sin coordenadas.
    if (type == FamilyNotification.type) {
      _family.add(FamilyNotification.fromData(data, opened: opened));
      return;
    }
    final bool quiet = data[_quietKey]?.toString() == 'true';
    _events.add(
      NotificationEnvelope(
        event: SeismicEvent.fromMap(data),
        critical: critical ?? (!quiet && _isCriticalStringMap(data)),
        followUp: followUp || quiet,
      ),
    );
  }

  Future<void> dispose() async {
    await Future.wait(
      _subscriptions.map((subscription) => subscription.cancel()),
    );
    await _events.close();
    await _family.close();
  }
}

Future<void> _initializeLocalPlugin(
  FlutterLocalNotificationsPlugin plugin, {
  DidReceiveNotificationResponseCallback? onResponse,
}) async {
  const InitializationSettings settings = InitializationSettings(
    android: AndroidInitializationSettings('ic_stat_seismik'),
    iOS: DarwinInitializationSettings(
      requestAlertPermission: false,
      requestBadgePermission: false,
      requestSoundPermission: false,
      requestCriticalPermission: false,
    ),
  );
  await plugin.initialize(
    settings: settings,
    onDidReceiveNotificationResponse: onResponse,
  );
  final AndroidFlutterLocalNotificationsPlugin? android = plugin
      .resolvePlatformSpecificImplementation<
        AndroidFlutterLocalNotificationsPlugin
      >();
  await android?.createNotificationChannel(_criticalChannel);
  await android?.createNotificationChannel(_updatesChannel);
}

/// Suena la alarma, salvo que ya haya sonado por el mismo sismo: entonces el
/// aviso llega como notificación normal. Devuelve si sonó.
Future<bool> _presentCritical(
  FlutterLocalNotificationsPlugin plugin,
  Map<String, dynamic> data,
  AlertMemory memory,
) async {
  if (await memory.alreadyRang(data)) {
    await _showQuietFollowUp(plugin, data);
    return false;
  }
  await memory.remember(data);
  await _showCriticalNotification(plugin, data);
  return true;
}

/// Identificador estable entre el isolate de fondo y la app: `hashCode` de un
/// String no está garantizado entre procesos.
int _notificationId(Map<String, dynamic> data) {
  final String id = (data['event_id'] ?? '').toString();
  if (id.isEmpty) return DateTime.now().millisecondsSinceEpoch.remainder(1 << 31);
  int hash = 0x811c9dc5;
  for (final int unit in utf8.encode(id)) {
    hash = ((hash ^ unit) * 0x01000193) & 0xffffffff;
  }
  return hash & 0x7fffffff;
}

Future<void> _showQuietFollowUp(
  FlutterLocalNotificationsPlugin plugin,
  Map<String, dynamic> data,
) async {
  final bool official = data['type']?.toString() == 'official_report_update';
  await plugin.show(
    id: _notificationId(data),
    title: official ? 'Reporte del sismo' : 'Nueva detección del mismo sismo',
    body: official
        ? _strongShakingBody(data)
        : 'La alarma ya sonó por este sismo. Revisa la app para ver los datos.',
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        SeismikConstants.updatesChannelId,
        'Reportes sísmicos oficiales',
        channelDescription:
            'Actualizaciones verificadas de servicios geológicos.',
        importance: Importance.defaultImportance,
        priority: Priority.defaultPriority,
      ),
      iOS: DarwinNotificationDetails(presentAlert: true, presentSound: false),
    ),
    payload: jsonEncode(<String, dynamic>{...data, _quietKey: 'true'}),
  );
}

Future<void> _showCriticalNotification(
  FlutterLocalNotificationsPlugin plugin,
  Map<String, dynamic> data,
) async {
  // Un reporte oficial sólo llega como alarma a quien quedó en la zona de
  // sacudida fuerte; para entonces el sismo ya pasó.
  final bool official = data['type']?.toString() == 'official_report_update';
  await plugin.show(
    id: _notificationId(data),
    title: official ? 'SISMO FUERTE EN TU ZONA' : '¡SISMO DETECTADO!',
    body: official
        ? _strongShakingBody(data)
        : 'Busca protección: agáchate, cúbrete y sujétate.',
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        SeismikConstants.criticalChannelId,
        'Alertas sísmicas críticas',
        channelDescription: 'Alertas inmediatas de detección sísmica Seismik.',
        importance: Importance.max,
        priority: Priority.max,
        category: AndroidNotificationCategory.alarm,
        fullScreenIntent: true,
        ongoing: true,
        autoCancel: false,
        // Si el mismo aviso se vuelve a publicar, actualiza el texto sin sonar.
        onlyAlertOnce: true,
        visibility: NotificationVisibility.public,
        sound: RawResourceAndroidNotificationSound('alarm'),
        audioAttributesUsage: AudioAttributesUsage.alarm,
      ),
      iOS: DarwinNotificationDetails(
        presentAlert: true,
        presentBadge: true,
        presentSound: true,
        sound: 'alarm.aiff',
        interruptionLevel: InterruptionLevel.critical,
        criticalSoundVolume: 1.0,
      ),
    ),
    payload: jsonEncode(data),
  );
}

String _strongShakingBody(Map<String, dynamic> data) {
  final double? magnitude = double.tryParse('${data['magnitude'] ?? ''}');
  final String place = (data['place'] ?? data['agency'] ?? '').toString();
  return <String>[
    if (magnitude != null) 'M ${magnitude.toStringAsFixed(1)}',
    if (place.isNotEmpty) place,
    'Se estima sacudida fuerte donde estás. Prepárate para réplicas.',
  ].join(' · ');
}

bool _isCritical(Map<String, dynamic> data) => _isCriticalStringMap(data);

bool _isFamily(Map<String, dynamic> data) =>
    data['type']?.toString() == FamilyNotification.type;

Future<void> _showFamilyNotification(
  FlutterLocalNotificationsPlugin plugin,
  RemoteMessage message,
) async {
  final Map<String, dynamic> data = Map<String, dynamic>.from(message.data);
  final FamilyNotification notice = FamilyNotification.fromData(
    data,
    opened: true,
  );
  await plugin.show(
    id: (data['event_id'] ?? DateTime.now().toIso8601String()).hashCode,
    title: message.notification?.title ?? notice.title,
    body: message.notification?.body ?? '',
    notificationDetails: const NotificationDetails(
      android: AndroidNotificationDetails(
        SeismikConstants.updatesChannelId,
        'Reportes sísmicos oficiales',
        importance: Importance.high,
        priority: Priority.high,
      ),
      iOS: DarwinNotificationDetails(presentAlert: true, presentSound: true),
    ),
    payload: jsonEncode(data),
  );
}

bool _isCriticalStringMap(Map<String, dynamic> data) =>
    data['channel_id']?.toString() == SeismikConstants.criticalChannelId ||
    data['critical']?.toString() == 'true' ||
    data['type']?.toString() == 'earthquake_candidate' ||
    data['type']?.toString() == 'crowdsourced_earthquake_candidate';
