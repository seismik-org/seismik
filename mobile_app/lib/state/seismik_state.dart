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

/// Ajustes que obligan a hablar con el servidor.
///
/// El tema, el color o el proveedor de mapas sólo cambian la interfaz. Antes
/// cualquier ajuste volvía a registrar el dispositivo y descargaba de nuevo el
/// historial y el catálogo de estaciones.
class _NetworkPreferences {
  _NetworkPreferences.of(MobileSettings settings)
    : crowdsourcing = settings.crowdsourcingEnabled,
      earlyAlerts = settings.receiveEarlyAlerts,
      officialUpdates = settings.receiveOfficialUpdates,
      notificationMagnitude = settings.minimumNotificationMagnitude,
      alertRadiusKm = settings.alertRadiusKm,
      historyDays = settings.historyDays,
      historyMagnitude = settings.minimumHistoryMagnitude,
      historySources = (settings.historySources.toList()..sort()).join(',');

  final bool crowdsourcing;
  final bool earlyAlerts;
  final bool officialUpdates;
  final double notificationMagnitude;
  final double alertRadiusKm;
  final int historyDays;
  final double historyMagnitude;
  final String historySources;

  bool alertFilterDiffers(_NetworkPreferences other) =>
      earlyAlerts != other.earlyAlerts ||
      officialUpdates != other.officialUpdates ||
      notificationMagnitude != other.notificationMagnitude ||
      alertRadiusKm != other.alertRadiusKm;

  bool historyFilterDiffers(_NetworkPreferences other) =>
      historyDays != other.historyDays ||
      historyMagnitude != other.historyMagnitude ||
      historySources != other.historySources;
}

class SeismikState extends ChangeNotifier with WidgetsBindingObserver {
  SeismikState({
    required this.settings,
    ApiClient? apiClient,
    NotificationService? notificationService,
    this.reportQueue = const OfflineReportQueue(),
    this.settingsDebounce = const Duration(milliseconds: 600),
  }) : api = apiClient ?? ApiClient(),
       notifications = notificationService ?? NotificationService() {
    accelerometer = AccelerometerService(
      apiClient: api,
      positionProvider: currentCoordinates,
    );
    _networkPreferences = _NetworkPreferences.of(settings);
    settings.addListener(_onSettingsChanged);
    WidgetsBinding.instance.addObserver(this);
  }

  /// Una ubicación del sistema con menos de esta edad basta para registrar
  /// las alertas, cuyos radios van de 50 a 600 km.
  static const Duration _freshLocationAge = Duration(minutes: 15);

  /// Distancia a partir de la cual conviene actualizar la geocerca registrada.
  static const double _reregisterDistanceMeters = 5000;

  /// Alertas recuperadas que se conservan al refrescar el historial.
  static const int _maxRecoveredAlerts = 50;

  final MobileSettings settings;
  final ApiClient api;
  final NotificationService notifications;
  final OfflineReportQueue reportQueue;

  /// Espera tras el último cambio de un ajuste antes de hablar con el servidor.
  final Duration settingsDebounce;

  late final AccelerometerService accelerometer;

  /// Aumenta con cada registro exitoso del dispositivo. Búsqueda de
  /// familiares lo escucha para asociar a la cuenta el token push nuevo.
  final ValueNotifier<int> registrations = ValueNotifier<int>(0);
  late _NetworkPreferences _networkPreferences;
  StreamSubscription<NotificationEnvelope>? _notificationSubscription;
  Timer? _alertPreferencesTimer;
  Timer? _historyFilterTimer;
  Future<void>? _refreshInFlight;
  bool _refreshRequestedAgain = false;
  Future<void>? _flushInFlight;
  Future<void>? _missedAlertsInFlight;
  List<SeismicEvent> _recoveredAlerts = const <SeismicEvent>[];
  bool _disposed = false;

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
    _notify();
    _notificationSubscription = notifications.events.listen(_onNotification);

    // Lo guardado en el teléfono aparece de inmediato y la red lo reemplaza en
    // cuanto responde. Antes el mapa quedaba vacío hasta terminar la ubicación,
    // el registro y dos descargas en serie.
    unawaited(_showCachedData());
    pendingReportCount = await _orDefault(reportQueue.pendingCount(), 0);

    // Toda apertura salvo la primera ya tiene sesión: los datos se piden en
    // paralelo con la ubicación y el registro, sin esperarlos.
    final bool hadSession = await _orDefault(api.hasDeviceSession(), false);
    if (hadSession) unawaited(refreshNetworkData());

    await Future.wait(<Future<void>>[
      _initializeNotifications(),
      _resolveLocationSafely(),
    ]);
    initializing = false;
    _notify();

    if (position != null) {
      final bool registered = await _registerAndStartSensors();
      // Sin sesión previa, o con una que el servidor ya no aceptaba, los datos
      // se vuelven a pedir con la sesión recién emitida.
      if (registered && (!hadSession || !networkOnline)) {
        unawaited(refreshNetworkData());
      }
    } else if (!hadSession) {
      unawaited(refreshNetworkData());
    }
  }

  Future<void> _showCachedData() async {
    final Future<List<SeismicEvent>> cachedEvents = _orDefault(
      api.readCachedEvents(),
      const <SeismicEvent>[],
    );
    final Future<List<SeismicStation>> cachedStations = _orDefault(
      api.readCachedStations(),
      const <SeismicStation>[],
    );
    final List<SeismicEvent> events = await cachedEvents;
    final List<SeismicStation> loadedStations = await cachedStations;
    if (_disposed) return;
    bool changed = false;
    // La red pudo responder antes que el disco: nunca se pisan datos frescos.
    if (recentEvents.isEmpty && events.isNotEmpty) {
      recentEvents = events;
      changed = true;
    }
    if (stations.isEmpty && loadedStations.isNotEmpty) {
      stations = loadedStations;
      changed = true;
    }
    if (changed) _notify();
  }

  Future<void> _initializeNotifications() async {
    try {
      await notifications.initialize();
    } catch (error) {
      statusMessage = 'Notificaciones pendientes: $error';
      _notify();
    }
  }

  Future<void> _resolveLocationSafely() async {
    try {
      await _resolveLocation();
    } catch (error) {
      statusMessage = 'Ubicación pendiente: $error';
      _notify();
    }
  }

  /// Devuelve si el registro terminó bien.
  Future<bool> _registerAndStartSensors() async {
    try {
      await _registerWithRetry();
    } catch (error) {
      statusMessage = 'Registro del dispositivo pendiente: $error';
      _notify();
      return false;
    }
    try {
      // Son independientes entre sí: no hay motivo para encadenarlos.
      await Future.wait(<Future<void>>[
        _syncCrowdsourcing(),
        syncMissedAlerts(),
        flushPendingReports(),
      ]);
    } catch (_) {
      // Cada uno informa su propio estado; el registro ya quedó hecho.
    }
    return true;
  }

  void _onSettingsChanged() {
    final _NetworkPreferences previous = _networkPreferences;
    final _NetworkPreferences next = _NetworkPreferences.of(settings);
    _networkPreferences = next;

    if (next.crowdsourcing != previous.crowdsourcing) {
      unawaited(_syncCrowdsourcing());
    }
    // El umbral de magnitud y el radio viven en el servidor: sin volver a
    // registrar el dispositivo, el filtro nuevo no llegaría al dispatcher. Se
    // espera a que la persona termine de ajustar para registrar una sola vez.
    if (next.alertFilterDiffers(previous)) {
      _alertPreferencesTimer?.cancel();
      _alertPreferencesTimer = Timer(
        settingsDebounce,
        () => unawaited(_reregisterPreferences()),
      );
    }
    if (next.historyFilterDiffers(previous)) {
      _historyFilterTimer?.cancel();
      _historyFilterTimer = Timer(settingsDebounce, _requestHistoryRefresh);
    }
  }

  void _requestHistoryRefresh() {
    if (_disposed) return;
    if (_refreshInFlight != null) {
      // La descarga en curso usa el filtro anterior: se repite al terminar.
      _refreshRequestedAgain = true;
      return;
    }
    unawaited(refreshNetworkData());
  }

  Future<void> _reregisterPreferences() async {
    if (position == null || _disposed) return;
    try {
      await _registerWithRetry();
    } catch (error) {
      statusMessage = 'Preferencias de alerta sin sincronizar: $error';
      _notify();
    }
  }

  Future<void> _syncCrowdsourcing() async {
    try {
      if (settings.crowdsourcingEnabled && position != null) {
        await accelerometer.start();
      } else {
        await accelerometer.stop();
      }
    } catch (_) {
      // Un sensor ausente o bloqueado no debe impedir el resto del monitor.
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
        registrations.value++;
        return;
      } catch (_) {
        if (attempt == 2) rethrow;
        await Future<void>.delayed(Duration(seconds: attempt + 1));
      }
    }
  }

  /// Descarga el historial y el catálogo de estaciones.
  ///
  /// Volver a la app, tirar hacia abajo y cambiar un filtro pueden pedirlo a la
  /// vez: todas esas llamadas comparten una sola descarga.
  Future<void> refreshNetworkData() =>
      _refreshInFlight ??= _runRefreshes();

  Future<void> _runRefreshes() async {
    try {
      do {
        _refreshRequestedAgain = false;
        await _refreshOnce();
      } while (_refreshRequestedAgain && !_disposed);
    } finally {
      _refreshInFlight = null;
    }
  }

  Future<void> _refreshOnce() async {
    // Se piden a la vez. Las estaciones casi siempre salen de la caché y nunca
    // retrasan los sismos, que es lo que la persona espera ver.
    List<SeismicEvent>? loadedEvents;
    Object? failure;
    final Future<void> eventsReady = api
        .fetchRecentEvents(
          sourceIds: settings.historySources,
          days: settings.historyDays,
          minimumMagnitude: settings.minimumHistoryMagnitude,
        )
        .then<void>(
          (List<SeismicEvent> value) => loadedEvents = value,
          onError: (Object error) => failure = error,
        );
    final Future<List<SeismicStation>> stationsReady = _orDefault(
      api.fetchStations(),
      stations,
    );

    await eventsReady;
    if (_disposed) return;
    final List<SeismicEvent>? fresh = loadedEvents;
    if (fresh != null) {
      recentEvents = _withRecoveredAlerts(fresh);
      networkOnline = true;
      statusMessage = null;
    } else {
      networkOnline = false;
      statusMessage = 'Sincronización pendiente: $failure';
    }
    _notify();

    final List<SeismicStation> nextStations = await stationsReady;
    if (_disposed) return;
    // La misma lista significa el mismo catálogo: el mapa no se reconstruye.
    if (!identical(nextStations, stations) && nextStations.isNotEmpty) {
      stations = nextStations;
      _notify();
    }

    if (networkOnline) {
      await Future.wait(<Future<void>>[
        _orDefault(flushPendingReports(), null),
        syncMissedAlerts(),
      ]);
    }
  }

  List<SeismicEvent> _withRecoveredAlerts(List<SeismicEvent> history) {
    if (_recoveredAlerts.isEmpty) return history;
    final Set<String> ids = history.map((event) => event.id).toSet();
    final List<SeismicEvent> missing = _recoveredAlerts
        .where((event) => !ids.contains(event.id))
        .toList(growable: false);
    return missing.isEmpty ? history : <SeismicEvent>[...missing, ...history];
  }

  /// Al volver a primer plano, confirma que el servidor está disponible antes
  /// de vaciar la cola. Esto evita perder testimonios tras un corte de red
  /// prolongado y no reintenta a ciegas mientras el teléfono sigue offline.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !initializing) {
      unawaited(refreshNetworkData());
    }
  }

  /// Reenvía los reportes que quedaron guardados sin conexión.
  ///
  /// Dos vaciados simultáneos podrían leer la misma cola y enviar un reporte
  /// dos veces: se comparte el que ya está en curso.
  Future<void> flushPendingReports() =>
      _flushInFlight ??= _flushPendingReports().whenComplete(
        () => _flushInFlight = null,
      );

  Future<void> _flushPendingReports() async {
    final int previousCount = pendingReportCount;
    final String? previousMessage = syncMessage;
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
    // Casi siempre la cola está vacía: avisar igual reconstruía la pantalla
    // en cada refresco sin que nada hubiera cambiado.
    if (pendingReportCount != previousCount || syncMessage != previousMessage) {
      _notify();
    }
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
  Future<void> syncMissedAlerts() =>
      _missedAlertsInFlight ??= _syncMissedAlerts().whenComplete(
        () => _missedAlertsInFlight = null,
      );

  Future<void> _syncMissedAlerts() async {
    try {
      final List<SeismicEvent> missed = await api.fetchMissedAlerts();
      if (missed.isEmpty || _disposed) return;
      final Set<String> known = recentEvents.map((event) => event.id).toSet();
      final List<SeismicEvent> added = missed
          .where((event) => !known.contains(event.id))
          .toList(growable: false);
      if (added.isEmpty) return;
      // El cursor del servidor ya avanzó: si el historial se refresca, estas
      // alertas no volverían a llegar. Se guardan para no perderlas.
      _recoveredAlerts = <SeismicEvent>[
        ...added.reversed,
        ..._recoveredAlerts,
      ].take(_maxRecoveredAlerts).toList(growable: false);
      recentEvents = <SeismicEvent>[...added.reversed, ...recentEvents];
      syncMessage = added.length == 1
          ? 'Se recuperó 1 alerta recibida sin conexión.'
          : 'Se recuperaron ${added.length} alertas recibidas sin conexión.';
      _notify();
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
    _notify();
    return ReportResult.queued(
      reportId: reportId,
      locationPrecision: preciseLocation ? 'precise' : 'approximate',
      emergencyActionRecommended: emergencyActionRecommended,
    );
  }

  void selectEvent(SeismicEvent? event) {
    // Tocar el mapa sin nada seleccionado ya no reconstruye la pantalla.
    if (identical(selectedEvent, event)) return;
    selectedEvent = event;
    _notify();
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

    // La última ubicación del sistema llega al instante. Antes se esperaba un
    // GPS de alta precisión que en interiores tardaba hasta 10 s, y todo el
    // arranque quedaba detenido detrás de él.
    final Position? lastKnown = await _orDefault(
      Geolocator.getLastKnownPosition(),
      null,
    );
    if (lastKnown != null &&
        DateTime.now().difference(lastKnown.timestamp) < _freshLocationAge) {
      position = lastKnown;
      unawaited(_refinePosition());
      return;
    }
    try {
      position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 6),
        ),
      );
    } catch (_) {
      if (lastKnown == null) rethrow;
      position = lastKnown;
      unawaited(_refinePosition());
    }
  }

  /// Confirma la ubicación en segundo plano y actualiza la geocerca si la
  /// persona se movió desde la última posición conocida.
  Future<void> _refinePosition() async {
    final Position? before = position;
    try {
      final Position fresh = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 20),
        ),
      );
      if (_disposed) return;
      position = fresh;
      if (before != null &&
          !initializing &&
          Geolocator.distanceBetween(
                before.latitude,
                before.longitude,
                fresh.latitude,
                fresh.longitude,
              ) >
              _reregisterDistanceMeters) {
        unawaited(_reregisterPreferences());
      }
    } catch (_) {
      // Se conserva la ubicación anterior, que ya permitió registrarse.
    }
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
    _notify();
  }

  void dismissAlert() {
    activeAlert = null;
    _notify();
  }

  void clearOfficialEvent() {
    officialEvent = null;
    _notify();
  }

  /// Las descargas siguen en curso cuando la pantalla se cierra: avisar
  /// después de `dispose` lanzaría una excepción.
  void _notify() {
    if (!_disposed) notifyListeners();
  }

  static Future<T> _orDefault<T>(Future<T> future, T fallback) async {
    try {
      return await future;
    } catch (_) {
      return fallback;
    }
  }

  @override
  void dispose() {
    _disposed = true;
    _alertPreferencesTimer?.cancel();
    _historyFilterTimer?.cancel();
    registrations.dispose();
    WidgetsBinding.instance.removeObserver(this);
    settings.removeListener(_onSettingsChanged);
    unawaited(_notificationSubscription?.cancel());
    unawaited(accelerometer.stop());
    unawaited(notifications.dispose());
    api.close();
    super.dispose();
  }
}
