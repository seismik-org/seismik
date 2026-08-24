import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/constants.dart';
import 'presentation/screens/alert_overlay.dart';
import 'presentation/screens/event_detail_screen.dart';
import 'presentation/screens/monitor_screen.dart';
import 'state/seismik_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SeismikConstants.validateBuildConfiguration();
  await Firebase.initializeApp();
  await FirebaseAppCheck.instance.activate(
    providerAndroid: kReleaseMode
        ? const AndroidPlayIntegrityProvider()
        : const AndroidDebugProvider(),
    providerApple: kReleaseMode
        ? const AppleAppAttestWithDeviceCheckFallbackProvider()
        : const AppleDebugProvider(),
  );
  runApp(const SeismikApp());
}

class SeismikApp extends StatelessWidget {
  const SeismikApp({super.key});

  @override
  Widget build(BuildContext context) => ChangeNotifierProvider<SeismikState>(
    create: (_) {
      final SeismikState state = SeismikState();
      unawaited(state.initialize());
      return state;
    },
    child: MaterialApp(
      title: SeismikConstants.appName,
      debugShowCheckedModeBanner: false,
      themeMode: ThemeMode.dark,
      darkTheme: ThemeData(
        brightness: Brightness.dark,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF1ECB7B),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF081018),
        cardTheme: const CardThemeData(color: Color(0xFF111E29)),
        useMaterial3: true,
      ),
      home: const _SeismikShell(),
    ),
  );
}

class _SeismikShell extends StatelessWidget {
  const _SeismikShell();

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    if (state.initializing) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final Widget base = state.officialEvent == null
        ? const MonitorScreen()
        : EventDetailScreen(
            event: state.officialEvent!,
            onClose: state.clearOfficialEvent,
          );
    if (state.activeAlert == null) return base;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        base,
        Material(
          child: AlertOverlay(
            event: state.activeAlert!,
            onDismiss: state.dismissAlert,
          ),
        ),
      ],
    );
  }
}
