import 'dart:async';

import 'package:flutter/widgets.dart';
import 'package:geolocator/geolocator.dart';

import '../data/models/citizen_report.dart';
import '../data/models/pending_report.dart';
import '../data/models/seismic_event.dart';
import '../data/models/station.dart';
import '../services/accelerometer_service.dart';
import '../services/api_client.dart';
import '../services/notification_service.dart';
import '../services/offline_queue.dart';
import 'mobile_settings.dart';

class SeismikState extends ChangeNotifier with WidgetsBindingObserver {
  SeismikState({
    required this.settings,
    ApiClient? apiClient,
    NotificationService? notificationService,
    this.reportQueue = const OfflineReportQueue(),
  }) : api = apiClient ?? ApiClient(),
       notifications = notificationService ?? NotificationService() {
    accelerometer = AccelerometerService(
      apiClient: api,
      positionProvider: currentCoordinates,
    );
    settings.addListener(_onSettingsChanged);
    WidgetsBinding.instance.addObserver(this);
  }

  final MobileSettings settings;
  final ApiClient api;
  final NotificationService notifications;
  final OfflineReportQueue reportQueue;
  late final AccelerometerService accelerometer;
  StreamSubscription<NotificationEnvelope>? _notificationSubscription;
  bool _resumeSyncInProgress = false;

  bool initializing = true;
  bool networkOnline = false;
  String? statusMessage;
  Position? position;
  List<SeismicStation> stations = <SeismicStation>[];
  List<SeismicEvent> recentEvents = <SeismicEvent>[];
  SeismicEvent? activeAlert;
  SeismicEvent? officialEvent;
  SeismicEvent? selectedEvent;
  int pendingReportCount = 0;
  String? syncMessage;

  Future<void> initialize() async {
    statusMessage = 'Conectando servicios en segundo plano…';
    notifyListeners();
    _notificationSubscription = notifications.events.listen(_onNotification);
    pendingReportCount = await reportQueue.pendingCount();

    final Future<void> notificationReady = _initializeNotifications();
    final Future<void> locationReady = _resolveLocationSafely();

    // The monitor endpoints require the short-lived device session created by
    // registration. Starting both requests here used to race a fresh install:
    // they failed before registration and Dart surfaced only ParallelWaitError.
    await Future.wait(<Future<void>>[notificationReady, locationReady]);
    initializing = false;
    notifyListeners();
    if (position != null) {
      await _registerAndStartSensors();
    }
    unawaited(refreshNetworkData());
  }

  Future<void> _initializeNotifications() async {
    try {
      await notifications.initialize();
    } catch (error) {
      statusMessage = 'Notificaciones pendientes: $error';
      notifyListeners();
    }
  }

  Future<void> _resolveLocationSafely() async {
    try {
      await _resolveLocation();
    } catch (error) {
      statusMessage = 'Ubicación pendiente: $error';
      notifyListeners();
    }
  }

  Future<void> _registerAndStartSensors() async {
    try {
      await _registerWithRetry();
      await _syncCrowdsourcing();
      await syncMissedAlerts();
      await flushPendingReports();
    } catch (error) {
      statusMessage = 'Registro del dispositivo pendiente: $error';
      notifyListeners();
    }
  }

  void _onSettingsChanged() {
    unawaited(_syncCrowdsourcing());
    // El umbral de magnitud y el radio viven en el servidor: sin volver a
    // registrar el dispositivo, el filtro nuevo no llegaría al dispatcher.
    unawaited(_reregisterPreferences());
    unawaited(refreshNetworkData());
  }

  Future<void> _reregisterPreferences() async {
    if (position == null) return;
    try {
      await _registerWithRetry();
    } catch (error) {
      statusMessage = 'Preferencias de alerta sin sincronizar: $error';
      notifyListeners();
    }
  }

  Future<void> _syncCrowdsourcing() async {
    if (settings.crowdsourcingEnabled && position != null) {
      await accelerometer.start();
    } else {
      await accelerometer.stop();
    }
  }

  Future<void> _registerWithRetry() async {
    final Position current = position!;
    for (int attempt = 0; attempt < 3; attempt++) {
      try {
        await api.registerDevice(
          latitude: current.latitude,
          longitude: current.longitude,
          receiveEarlyAlerts: settings.receiveEarlyAlerts,
          receiveOfficialUpdates: settings.receiveOfficialUpdates,
          minimumNotificationMagnitude: settings.minimumNotificationMagnitude,
          alertRadiusKm: settings.alertRadiusKm,
        );
        return;
      } catch (_) {
        if (attempt == 2) rethrow;
        await Future<void>.delayed(Duration(seconds: attempt + 1));
      }
    }
  }

  Future<void> refreshNetworkData() async {
    try {
      // Await independently so a failed source reports its useful error rather
      // than the opaque ParallelWaitError emitted by record.wait.
      final List<SeismicStation> loadedStations = await api.fetchStations();
      final List<SeismicEvent> loadedEvents = await api.fetchRecentEvents(
        sourceIds: settings.historySources,
        days: settings.historyDays,
        minimumMagnitude: settings.minimumHistoryMagnitude,
      );
      stations = loadedStations;
      recentEvents = loadedEvents;
      networkOnline = true;
      statusMessage = null;
    } catch (error) {
      networkOnline = false;
      statusMessage = 'Sincronización pendiente: $error';
    }
    notifyListeners();
    if (networkOnline) {
      await flushPendingReports();
      await syncMissedAlerts();
    }
  }

  /// Al volver a primer plano, confirma que el servidor está disponible antes
  /// de vaciar la cola. Esto evita perder testimonios tras un corte de red
  /// prolongado y no reintenta a ciegas mientras el teléfono sigue offline.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !initializing) {
      unawaited(_syncAfterResume());
    }
  }

  Future<void> _syncAfterResume() async {
    if (_resumeSyncInProgress) return;
    _resumeSyncInProgress = true;
    try {
      await refreshNetworkData();
    } finally {
      _resumeSyncInProgress = false;
    }
  }

  /// Reenvía los reportes que quedaron guardados sin conexión.
  Future<void> flushPendingReports() async {
    final QueueFlushResult result = await reportQueue.flush(_sendPending);
    pendingReportCount = result.remaining;
    if (result.sent > 0) {
      syncMessage = result.sent == 1
          ? 'Se envió 1 reporte guardado sin conexión.'
          : 'Se enviaron ${result.sent} reportes guardados sin conexión.';
    } else if (result.remaining > 0) {
      syncMessage = result.remaining == 1
          ? '1 reporte espera conexión para enviarse.'
          : '${result.remaining} reportes esperan conexión para enviarse.';
    } else if (result.changed) {
      syncMessage = null;
    }
    notifyListeners();
  }

  Future<void> _sendPending(PendingReport report) async {
    try {
      await api.sendReport(report.kind.path, report.payload);
    } on SeismikApiException catch (error) {
      if (error.isPermanent) {
        throw PermanentReportRejection(error.message);
      }
      rethrow;
    }
  }

  /// Recupera del servidor las alertas emitidas mientras no hubo conexión.
  Future<void> syncMissedAlerts() async {
    try {
      final List<SeismicEvent> missed = await api.fetchMissedAlerts();
      if (missed.isEmpty) return;
      final Set<String> known = recentEvents.map((event) => event.id).toSet();
      final List<SeismicEvent> added = missed
          .where((event) => !known.contains(event.id))
          .toList(growable: false);
      if (added.isEmpty) return;
      recentEvents = <SeismicEvent>[...added.reversed, ...recentEvents];
      syncMessage = added.length == 1
          ? 'Se recuperó 1 alerta recibida sin conexión.'
          : 'Se recuperaron ${added.length} alertas recibidas sin conexión.';
      notifyListeners();
    } catch (_) {
      // La bitácora es un complemento: su ausencia no degrada el monitor.
    }
  }

  /// Envía el reporte y, si no hay red, lo guarda para sincronizarlo después.
  Future<ReportResult> submitReport({
    required PendingReportKind kind,
    required Map<String, dynamic> payload,
    required bool preciseLocation,
    bool emergencyActionRecommended = false,
  }) async {
    try {
      final ReportResult result = await api.sendReport(kind.path, payload);
      await flushPendingReports();
      return result;
    } on SeismikApiException catch (error) {
      if (error.isPermanent) rethrow;
      return _queueReport(
        kind: kind,
        payload: payload,
        preciseLocation: preciseLocation,
        emergencyActionRecommended: emergencyActionRecommended,
      );
    } catch (_) {
      return _queueReport(
        kind: kind,
        payload: payload,
        preciseLocation: preciseLocation,
        emergencyActionRecommended: emergencyActionRecommended,
      );
    }
  }

  Future<ReportResult> _queueReport({
    required PendingReportKind kind,
    required Map<String, dynamic> payload,
    required bool preciseLocation,
    required bool emergencyActionRecommended,
  }) async {
    final String reportId = (payload['report_id'] ?? '').toString();
    await reportQueue.enqueue(
      PendingReport(
        reportId: reportId,
        kind: kind,
        payload: payload,
        queuedAt: DateTime.now().toUtc(),
      ),
    );
    pendingReportCount = await reportQueue.pendingCount();
    notifyListeners();
    return ReportResult.queued(
      reportId: reportId,
      locationPrecision: preciseLocation ? 'precise' : 'approximate',
      emergencyActionRecommended: emergencyActionRecommended,
    );
  }

  void selectEvent(SeismicEvent? event) {
    selectedEvent = event;
    notifyListeners();
  }

  Future<void> _resolveLocation() async {
    if (!await Geolocator.isLocationServiceEnabled()) {
      statusMessage = 'Activa la ubicación para geocercas y crowdsourcing.';
      return;
    }
    LocationPermission permission = await Geolocator.checkPermission();
    if (permission == LocationPermission.denied) {
      permission = await Geolocator.requestPermission();
    }
    if (permission == LocationPermission.denied ||
        permission == LocationPermission.deniedForever) {
      statusMessage = 'Ubicación no autorizada.';
      return;
    }
    position = await Geolocator.getCurrentPosition(
      locationSettings: const LocationSettings(
        accuracy: LocationAccuracy.high,
        timeLimit: Duration(seconds: 10),
      ),
    );
  }

  Future<({double latitude, double longitude})?> currentCoordinates() async {
    final Position? cached = position;
    if (cached != null &&
        DateTime.now().difference(cached.timestamp) <
            const Duration(minutes: 2)) {
      return (latitude: cached.latitude, longitude: cached.longitude);
    }
    try {
      position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.high,
        ),
      );
      return (latitude: position!.latitude, longitude: position!.longitude);
    } catch (_) {
      return cached == null
          ? null
          : (latitude: cached.latitude, longitude: cached.longitude);
    }
  }

  void _onNotification(NotificationEnvelope envelope) {
    if (envelope.critical) {
      activeAlert = envelope.event;
    } else if (envelope.event.isOfficial) {
      officialEvent = envelope.event;
      recentEvents = <SeismicEvent>[envelope.event, ...recentEvents];
    }
    notifyListeners();
  }

  void dismissAlert() {
    activeAlert = null;
    notifyListeners();
  }

  void clearOfficialEvent() {
    officialEvent = null;
    notifyListeners();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    settings.removeListener(_onSettingsChanged);
    unawaited(_notificationSubscription?.cancel());
    unawaited(accelerometer.stop());
    unawaited(notifications.dispose());
    api.close();
    super.dispose();
  }
}
