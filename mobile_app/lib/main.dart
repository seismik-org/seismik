import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'core/constants.dart';
import 'core/theme.dart';
import 'presentation/screens/alert_overlay.dart';
import 'presentation/screens/damage_report_screen.dart';
import 'presentation/screens/event_detail_screen.dart';
import 'presentation/screens/felt_report_screen.dart';
import 'presentation/screens/monitor_screen.dart';
import 'presentation/screens/settings_screen.dart';
import 'services/material_you_service.dart';
import 'state/seismik_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  SeismikConstants.validateBuildConfiguration();
  final Color? exactSystemAccent = await MaterialYouService.readExactAccent();
  await Firebase.initializeApp();
  await FirebaseAppCheck.instance.activate(
    providerAndroid: kReleaseMode
        ? const AndroidPlayIntegrityProvider()
        : const AndroidDebugProvider(),
    providerApple: kReleaseMode
        ? const AppleAppAttestWithDeviceCheckFallbackProvider()
        : const AppleDebugProvider(),
  );
  runApp(SeismikApp(exactSystemAccent: exactSystemAccent));
}

class SeismikApp extends StatelessWidget {
  const SeismikApp({this.exactSystemAccent, super.key});

  final Color? exactSystemAccent;

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
      themeMode: ThemeMode.system,
      theme: SeismikTheme.fromScheme(
        SeismikTheme.scheme(
          brightness: Brightness.light,
          exactSystemAccent: exactSystemAccent,
        ),
      ),
      darkTheme: SeismikTheme.fromScheme(
        SeismikTheme.scheme(
          brightness: Brightness.dark,
          exactSystemAccent: exactSystemAccent,
        ),
      ),
      home: _SeismikShell(exactSystemAccent: exactSystemAccent),
    ),
  );
}

class _SeismikShell extends StatefulWidget {
  const _SeismikShell({required this.exactSystemAccent});

  final Color? exactSystemAccent;

  @override
  State<_SeismikShell> createState() => _SeismikShellState();
}

class _SeismikShellState extends State<_SeismikShell> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    if (state.initializing) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    final Widget base;
    if (state.officialEvent != null) {
      base = EventDetailScreen(
        event: state.officialEvent!,
        onClose: state.clearOfficialEvent,
      );
    } else {
      final event = state.recentEvents.isEmpty
          ? null
          : state.recentEvents.first;
      base = Stack(
        fit: StackFit.expand,
        children: <Widget>[
          IndexedStack(
            index: _selectedIndex,
            children: <Widget>[
              const MonitorScreen(),
              FeltReportScreen(event: event),
              DamageReportScreen(event: event),
              SettingsScreen(
                activeAccent: Theme.of(context).colorScheme.primary,
                usesSystemAccent: widget.exactSystemAccent != null,
              ),
            ],
          ),
          Positioned(
            left: 14,
            right: 14,
            bottom: 12,
            child: SafeArea(
              top: false,
              child: _FloatingMenu(
                selectedIndex: _selectedIndex,
                onSelected: (index) => setState(() => _selectedIndex = index),
              ),
            ),
          ),
        ],
      );
    }
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

class _FloatingMenu extends StatelessWidget {
  const _FloatingMenu({required this.selectedIndex, required this.onSelected});

  final int selectedIndex;
  final ValueChanged<int> onSelected;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(34),
        boxShadow: const <BoxShadow>[
          BoxShadow(
            color: Color(0x66000000),
            blurRadius: 24,
            offset: Offset(0, 8),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(34),
        child: NavigationBar(
          height: 76,
          selectedIndex: selectedIndex,
          onDestinationSelected: onSelected,
          backgroundColor: colors.surfaceContainerHigh,
          destinations: const <NavigationDestination>[
            NavigationDestination(
              icon: Icon(Icons.history_rounded),
              selectedIcon: Icon(Icons.history_rounded),
              label: 'Historial',
              tooltip: 'Historial de Sismos',
            ),
            NavigationDestination(
              icon: Icon(Icons.vibration_rounded),
              selectedIcon: Icon(Icons.vibration_rounded),
              label: 'Sismo sentido',
            ),
            NavigationDestination(
              icon: Icon(Icons.home_work_outlined),
              selectedIcon: Icon(Icons.home_work_rounded),
              label: 'Daños',
              tooltip: 'Reporte de daños',
            ),
            NavigationDestination(
              icon: Icon(Icons.tune_rounded),
              selectedIcon: Icon(Icons.tune_rounded),
              label: 'Configuración',
            ),
          ],
        ),
      ),
    );
  }
}
