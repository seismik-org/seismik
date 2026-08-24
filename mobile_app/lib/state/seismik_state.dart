import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:geolocator/geolocator.dart';

import '../data/models/seismic_event.dart';
import '../data/models/station.dart';
import '../services/accelerometer_service.dart';
import '../services/api_client.dart';
import '../services/notification_service.dart';

class SeismikState extends ChangeNotifier {
  SeismikState() : api = ApiClient(), notifications = NotificationService() {
    accelerometer = AccelerometerService(
      apiClient: api,
      positionProvider: currentCoordinates,
    );
  }

  final ApiClient api;
  final NotificationService notifications;
  late final AccelerometerService accelerometer;
  StreamSubscription<NotificationEnvelope>? _notificationSubscription;

  bool initializing = true;
  bool networkOnline = false;
  String? statusMessage;
  Position? position;
  List<SeismicStation> stations = <SeismicStation>[];
  List<SeismicEvent> recentEvents = <SeismicEvent>[];
  SeismicEvent? activeAlert;
  SeismicEvent? officialEvent;

  Future<void> initialize() async {
    try {
      await notifications.initialize();
      _notificationSubscription = notifications.events.listen(_onNotification);
      await _resolveLocation();
      if (position != null) {
        await _registerWithRetry();
        await accelerometer.start();
      }
      await refreshNetworkData();
    } catch (error) {
      statusMessage = 'Inicialización parcial: $error';
    } finally {
      initializing = false;
      notifyListeners();
    }
  }

  Future<void> _registerWithRetry() async {
    final Position current = position!;
    for (int attempt = 0; attempt < 3; attempt++) {
      try {
        await api.registerDevice(
          latitude: current.latitude,
          longitude: current.longitude,
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
      final (List<SeismicStation>, List<SeismicEvent>) response = await (
        api.fetchStations(),
        api.fetchRecentEvents(),
      ).wait;
      stations = response.$1;
      recentEvents = response.$2;
      networkOnline = true;
      statusMessage = null;
    } catch (error) {
      networkOnline = false;
      statusMessage = 'Sincronización pendiente: $error';
    }
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
    unawaited(_notificationSubscription?.cancel());
    unawaited(accelerometer.stop());
    unawaited(notifications.dispose());
    api.close();
    super.dispose();
  }
}
