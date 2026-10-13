import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';

/// Serializes dependent SDK startup; failure is retryable, never cached forever.
class ServiceReadiness {
  ServiceReadiness(this.start);
  final Future<void> Function() start;
  Future<void>? _pending;
  bool _ready = false;

  Future<void> ensureReady() {
    if (_ready) return Future<void>.value();
    return _pending ??= _run();
  }

  Future<void> _run() async {
    try {
      await Future<void>.sync(start);
      _ready = true;
    } finally {
      _pending = null;
    }
  }
}

class FirebaseRuntime {
  static final readiness = ServiceReadiness(() async {
    if (Firebase.apps.isEmpty) await Firebase.initializeApp();
    await FirebaseAppCheck.instance.activate(
      providerAndroid: kReleaseMode
          ? const AndroidPlayIntegrityProvider()
          : const AndroidDebugProvider(),
      providerApple: kReleaseMode
          ? const AppleAppAttestWithDeviceCheckFallbackProvider()
          : const AppleDebugProvider(),
    );
  });

  static Future<void> ensureReady() => readiness.ensureReady();
}
