import 'dart:async';
import 'dart:convert';
import 'dart:math';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:url_launcher/url_launcher.dart';

import '../core/constants.dart';

/// Par PKCE generado en el teléfono (RFC 7636, método S256).
///
/// En Android cualquier app puede declarar el esquema `seismik://` y recibir el
/// código de un solo uso. El servidor sólo lo canjea con este verificador, que
/// nunca sale del teléfono hasta el canje, así que un código robado no sirve.
class PkcePair {
  const PkcePair(this.verifier, this.challenge);

  factory PkcePair.generate([Random? random]) {
    final Random source = random ?? Random.secure();
    final List<int> bytes = List<int>.generate(48, (_) => source.nextInt(256));
    final String verifier = base64UrlEncode(bytes).replaceAll('=', '');
    return PkcePair(verifier, challengeFor(verifier));
  }

  static String challengeFor(String verifier) => base64UrlEncode(
    sha256.convert(ascii.encode(verifier)).bytes,
  ).replaceAll('=', '');

  final String verifier;
  final String challenge;
}

/// La persona cerró la ventana de inicio de sesión sin terminarlo.
class SignInCancelled implements Exception {
  const SignInCancelled();

  @override
  String toString() => 'Inicio de sesión cancelado';
}

abstract interface class OAuthAuthorizer {
  /// Abre el inicio de sesión y devuelve la URI de retorno con el código.
  Future<Uri> authorize({required String provider, required String challenge});

  void dispose();
}

typedef BrowserLauncher = Future<bool> Function(Uri uri);

/// Inicio de sesión en Custom Tabs con retorno a `seismik://auth/callback`.
///
/// El proveedor nunca entrega sus tokens a la app: `auth.seismik.org` devuelve
/// un código de un solo uso que la app canjea con su verificador PKCE.
class OAuthBrowserFlow implements OAuthAuthorizer {
  OAuthBrowserFlow({BrowserLauncher? launcher, MethodChannel? channel})
    : _launcher = launcher ?? _openCustomTab,
      _channel = channel ?? const MethodChannel(channelName) {
    _channel.setMethodCallHandler(_onNativeCall);
  }

  static const String channelName = 'com.seismik.app/oauth';

  /// Tiempo para volver con el código tras regresar a la app. Al cerrar la
  /// pestaña sin iniciar sesión no llega ningún retorno.
  static const Duration _returnGrace = Duration(milliseconds: 1500);

  final BrowserLauncher _launcher;
  final MethodChannel _channel;
  Completer<Uri>? _pending;
  AppLifecycleListener? _lifecycle;

  static Future<bool> _openCustomTab(Uri uri) =>
      launchUrl(uri, mode: LaunchMode.inAppBrowserView);

  @override
  Future<Uri> authorize({
    required String provider,
    required String challenge,
  }) async {
    _finish(error: const SignInCancelled());
    // Un retorno viejo de un intento abandonado no debe completar este.
    await _takePending(deliver: false);
    final Completer<Uri> completer = Completer<Uri>();
    _pending = completer;
    _lifecycle?.dispose();
    _lifecycle = AppLifecycleListener(onResume: _onResume);
    final Uri start = Uri.parse(
      '${SeismikConstants.authBaseUrl}/v1/oauth/authorize',
    ).replace(
      queryParameters: <String, String>{
        'provider': provider,
        'origin': 'app',
        'app_challenge': challenge,
      },
    );
    try {
      if (!await _launcher(start)) _finish(error: const SignInCancelled());
      return await completer.future.timeout(
        const Duration(minutes: 10),
        onTimeout: () => throw const SignInCancelled(),
      );
    } finally {
      if (identical(_pending, completer)) _pending = null;
      _lifecycle?.dispose();
      _lifecycle = null;
    }
  }

  Future<dynamic> _onNativeCall(MethodCall call) async {
    if (call.method == 'callbackAvailable') await _takePending();
    return null;
  }

  void _onResume() {
    unawaited(
      Future<void>.delayed(_returnGrace, () async {
        final Completer<Uri>? pending = _pending;
        if (pending == null || pending.isCompleted) return;
        if (await _takePending()) return;
        _finish(error: const SignInCancelled());
      }),
    );
  }

  Future<bool> _takePending({bool deliver = true}) async {
    String? raw;
    try {
      raw = await _channel.invokeMethod<String>('takePendingCallback');
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
    if (raw == null || raw.isEmpty) return false;
    if (deliver) _finish(uri: Uri.parse(raw));
    return true;
  }

  void _finish({Uri? uri, Object? error}) {
    final Completer<Uri>? pending = _pending;
    if (pending == null || pending.isCompleted) return;
    if (uri != null) {
      pending.complete(uri);
    } else {
      pending.completeError(error ?? const SignInCancelled());
    }
  }

  @override
  void dispose() {
    _finish(error: const SignInCancelled());
    _lifecycle?.dispose();
    _lifecycle = null;
    _channel.setMethodCallHandler(null);
  }
}
