import 'dart:async';

import 'package:flutter/foundation.dart';

import '../data/models/family_circle.dart';
import '../data/models/seismic_event.dart';
import '../data/models/seismik_account.dart';
import '../services/account_service.dart';
import '../services/api_client.dart';
import '../services/notification_service.dart';
import 'seismik_state.dart';

/// Cuenta y círculo familiar de la persona.
///
/// Tras un sismo cada integrante avisa si está bien o necesita ayuda. Ese aviso
/// comparte su ubicación con la familia durante unas horas y les llega como
/// notificación. Sin cuenta no hay forma de saber quién es quién.
class FamilyState extends ChangeNotifier {
  FamilyState({required this.seismik, OAuthAuthorizer? authorizer})
    : _authorizer = authorizer ?? OAuthBrowserFlow() {
    seismik.registrations.addListener(_onDeviceRegistered);
    _notifications = seismik.notifications.familyUpdates.listen(
      _onFamilyNotification,
    );
  }

  final SeismikState seismik;
  final OAuthAuthorizer _authorizer;
  StreamSubscription<FamilyNotification>? _notifications;
  bool _disposed = false;

  SeismikAccount? account;
  FamilyCircle? circle;
  bool loading = false;
  bool signingIn = false;
  bool reporting = false;
  String? error;

  /// Sismo tras el cual la persona pidió avisar a su familia desde la alerta.
  SeismicEvent? checkInEvent;

  /// Aumenta cuando hay que mostrar la pestaña Familia: se tocó un aviso
  /// familiar o «Avisar a mi familia» en la alerta.
  final ValueNotifier<int> openRequests = ValueNotifier<int>(0);

  ApiClient get _api => seismik.api;

  Future<void> initialize() async {
    try {
      account = await _api.currentAccount();
    } catch (_) {
      account = null;
    }
    _notify();
    if (account == null) return;
    await _linkDeviceQuietly();
    await refresh();
  }

  Future<void> signIn({String provider = 'google'}) async {
    if (signingIn) return;
    signingIn = true;
    error = null;
    _notify();
    try {
      final PkcePair pkce = PkcePair.generate();
      final Uri callback = await _authorizer.authorize(
        provider: provider,
        challenge: pkce.challenge,
      );
      final String code = callback.queryParameters['code'] ?? '';
      if (code.isEmpty) throw const SignInCancelled();
      account = await _api.exchangeOAuthCode(
        code: code,
        verifier: pkce.verifier,
      );
      signingIn = false;
      _notify();
      // Se enlaza antes de leer el círculo: así el que este teléfono tenía
      // antes de exigir cuenta ya aparece como el de la persona.
      await _linkDeviceQuietly();
      await refresh();
    } on SignInCancelled {
      // Cerrar la ventana de inicio de sesión no es un error que mostrar.
    } catch (_) {
      error =
          'No se pudo iniciar sesión. Revisa tu conexión e inténtalo de nuevo.';
    } finally {
      signingIn = false;
      _notify();
    }
  }

  Future<void> signOut() async {
    try {
      // Sin esto el teléfono seguiría recibiendo los avisos de la familia.
      await _api.unlinkDeviceFromAccount();
    } catch (_) {
      // Cerrar sesión funciona también sin red.
    }
    await _api.clearAccount();
    account = null;
    circle = null;
    checkInEvent = null;
    error = null;
    _notify();
  }

  Future<void> refresh() async {
    if (account == null) return;
    loading = true;
    _notify();
    try {
      circle = await _api.fetchFamilyCircle();
      error = null;
    } on SeismikApiException catch (failure) {
      if (failure.isUnauthorized) {
        await _expireSession();
      } else {
        error = 'No fue posible actualizar tu familia. Revisa tu conexión.';
      }
    } catch (_) {
      error = 'No fue posible actualizar tu familia. Revisa tu conexión.';
    } finally {
      loading = false;
      _notify();
    }
  }

  Future<void> createCircle({
    required String displayName,
    required String circleName,
  }) async {
    await _api.createFamilyCircle(
      displayName: displayName,
      circleName: circleName,
    );
    await refresh();
  }

  Future<void> joinCircle({
    required String inviteCode,
    required String displayName,
  }) async {
    await _api.joinFamilyCircle(
      inviteCode: inviteCode,
      displayName: displayName,
    );
    await refresh();
  }

  Future<String> createInvitation(String displayName) =>
      _api.createFamilyInvitation(displayName);

  Future<void> stopSharingLocation() async {
    await _api.stopSharingFamilyLocation();
    await refresh();
  }

  /// «Estoy bien» o «Necesito ayuda». Devuelve si se pudo incluir la ubicación.
  Future<bool> reportStatus({
    required bool needsHelp,
    bool precise = false,
    String? message,
  }) async {
    reporting = true;
    _notify();
    try {
      // Tras un sismo no se espera indefinidamente al GPS: si tarda, vale la
      // última ubicación conocida, y sin ninguna el aviso sale igual.
      final ({double latitude, double longitude})? coordinates = await seismik
          .currentCoordinates()
          .timeout(const Duration(seconds: 8), onTimeout: _lastKnownCoordinates);
      await _api.reportFamilyStatus(
        needsHelp: needsHelp,
        message: message,
        eventId: checkInEvent?.id,
        latitude: coordinates?.latitude,
        longitude: coordinates?.longitude,
        precise: precise,
      );
      checkInEvent = null;
      unawaited(refresh());
      return coordinates != null;
    } on SeismikApiException catch (failure) {
      if (failure.isUnauthorized) await _expireSession();
      rethrow;
    } finally {
      reporting = false;
      _notify();
    }
  }

  /// La persona tocó «Avisar a mi familia» en la alerta de un sismo.
  void requestCheckIn(SeismicEvent event) {
    checkInEvent = event;
    _notify();
    openRequests.value++;
  }

  void dismissCheckIn() {
    checkInEvent = null;
    _notify();
  }

  ({double latitude, double longitude})? _lastKnownCoordinates() {
    final position = seismik.position;
    return position == null
        ? null
        : (latitude: position.latitude, longitude: position.longitude);
  }

  void _onDeviceRegistered() {
    // Cada registro puede traer un token push nuevo: la cuenta debe apuntar a
    // este teléfono para que le lleguen los avisos de la familia.
    if (account != null) unawaited(_linkDeviceQuietly());
  }

  Future<void> _linkDeviceQuietly() async {
    try {
      await _api.linkDeviceToAccount();
    } on SeismikApiException catch (failure) {
      if (failure.isUnauthorized) await _expireSession();
    } catch (_) {
      // Sin registro todavía; se reintenta cuando el teléfono se registre.
    }
  }

  void _onFamilyNotification(FamilyNotification notice) {
    if (notice.opened) openRequests.value++;
    unawaited(refresh());
  }

  Future<void> _expireSession() async {
    await _api.clearAccount();
    account = null;
    circle = null;
    error = 'Tu sesión venció. Inicia sesión de nuevo para ver a tu familia.';
    _notify();
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    seismik.registrations.removeListener(_onDeviceRegistered);
    unawaited(_notifications?.cancel());
    openRequests.dispose();
    _authorizer.dispose();
    super.dispose();
  }
}
