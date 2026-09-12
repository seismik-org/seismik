import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:dynamic_color/dynamic_color.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'core/constants.dart';
import 'core/platform.dart';
import 'core/theme.dart';
import 'data/models/seismic_event.dart';
import 'presentation/screens/alert_overlay.dart';
import 'presentation/screens/damage_report_screen.dart';
import 'presentation/screens/event_detail_screen.dart';
import 'presentation/screens/felt_report_screen.dart';
import 'presentation/screens/ios_settings_screen.dart';
import 'presentation/screens/monitor_screen.dart';
import 'presentation/screens/settings_screen.dart';
import 'state/mobile_settings.dart';
import 'state/seismik_state.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  SeismikConstants.validateBuildConfiguration();
  final MobileSettings settings = MobileSettings();
  await settings.load();
  runApp(SeismikApp(settings: settings));
}

class SeismikApp extends StatelessWidget {
  const SeismikApp({required this.settings, super.key});

  final MobileSettings settings;

  @override
  Widget build(BuildContext context) => MultiProvider(
    providers: <ChangeNotifierProvider<ChangeNotifier>>[
      ChangeNotifierProvider<MobileSettings>.value(value: settings),
      ChangeNotifierProvider<SeismikState>(
        create: (_) {
          final SeismikState state = SeismikState(settings: settings);
          unawaited(state.initialize());
          return state;
        },
      ),
    ],
    child: DynamicColorBuilder(
      builder: (ColorScheme? systemLight, ColorScheme? systemDark) {
        return Consumer<MobileSettings>(
          builder: (context, settings, _) {
            final bool useSystem =
                settings.useDynamicColor &&
                systemLight != null &&
                systemDark != null;
            final ColorScheme light = useSystem
                ? systemLight
                : SeismikTheme.scheme(brightness: Brightness.light);
            final ColorScheme dark = useSystem
                ? systemDark
                : SeismikTheme.scheme(brightness: Brightness.dark);
            return MaterialApp(
              title: SeismikConstants.appName,
              debugShowCheckedModeBanner: false,
              themeMode: settings.themeMode,
              theme: SeismikTheme.fromScheme(light),
              darkTheme: SeismikTheme.fromScheme(dark),
              builder: (context, child) {
                final bool darkMode =
                    Theme.of(context).brightness == Brightness.dark;
                return AnnotatedRegion<SystemUiOverlayStyle>(
                  value: SystemUiOverlayStyle(
                    statusBarColor: Colors.transparent,
                    statusBarIconBrightness: darkMode
                        ? Brightness.light
                        : Brightness.dark,
                    systemNavigationBarColor: Colors.transparent,
                    systemNavigationBarDividerColor: Colors.transparent,
                    systemNavigationBarIconBrightness: darkMode
                        ? Brightness.light
                        : Brightness.dark,
                    systemNavigationBarContrastEnforced: false,
                  ),
                  child: child ?? const SizedBox.shrink(),
                );
              },
              home: _SeismikShell(dynamicColorAvailable: systemLight != null),
            );
          },
        );
      },
    ),
  );
}

class _SeismikShell extends StatefulWidget {
  const _SeismikShell({required this.dynamicColorAvailable});

  final bool dynamicColorAvailable;

  @override
  State<_SeismikShell> createState() => _SeismikShellState();
}

class _SeismikShellState extends State<_SeismikShell> {
  int _selectedIndex = 0;

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return _IosSeismikShell(
        dynamicColorAvailable: widget.dynamicColorAvailable,
      );
    }
    // Sólo lo que el marco necesita. Con `watch`, cada aviso del estado (un
    // reporte en cola, un refresco, un toque en el mapa) reconstruía a la vez
    // todas las pestañas.
    final SeismicEvent? officialEvent = context
        .select<SeismikState, SeismicEvent?>((s) => s.officialEvent);
    final SeismicEvent? activeAlert = context
        .select<SeismikState, SeismicEvent?>((s) => s.activeAlert);
    final SeismicEvent? latestEvent = context
        .select<SeismikState, SeismicEvent?>(
          (s) => s.recentEvents.isEmpty ? null : s.recentEvents.first,
        );
    final SeismikState state = Provider.of<SeismikState>(
      context,
      listen: false,
    );
    final Widget base;
    if (officialEvent != null) {
      base = EventDetailScreen(
        event: officialEvent,
        onClose: state.clearOfficialEvent,
      );
    } else {
      final bool keyboardVisible = MediaQuery.viewInsetsOf(context).bottom > 0;
      base = Scaffold(
        resizeToAvoidBottomInset: true,
        body: IndexedStack(
          index: _selectedIndex,
          children: <Widget>[
            const MonitorScreen(),
            FeltReportScreen(event: latestEvent),
            DamageReportScreen(event: latestEvent),
            SettingsScreen(dynamicColorAvailable: widget.dynamicColorAvailable),
          ],
        ),
        bottomNavigationBar: keyboardVisible
            ? null
            : Padding(
                padding: const EdgeInsets.fromLTRB(14, 4, 14, 10),
                child: SafeArea(
                  top: false,
                  minimum: const EdgeInsets.only(bottom: 2),
                  child: _FloatingMenu(
                    selectedIndex: _selectedIndex,
                    onSelected: (index) =>
                        setState(() => _selectedIndex = index),
                  ),
                ),
              ),
      );
    }
    if (activeAlert == null) return base;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        base,
        Material(
          child: AlertOverlay(
            event: activeAlert,
            onDismiss: state.dismissAlert,
          ),
        ),
      ],
    );
  }
}

/// iPhone uses the native tab bar and navigation rhythm rather than the
/// floating Material navigation used by Android.  The feature state is shared;
/// only the platform presentation changes.
class _IosSeismikShell extends StatelessWidget {
  const _IosSeismikShell({required this.dynamicColorAvailable});

  final bool dynamicColorAvailable;

  @override
  Widget build(BuildContext context) {
    // Sólo lo que el marco necesita. Con `watch`, cada aviso del estado (un
    // reporte en cola, un refresco, un toque en el mapa) reconstruía a la vez
    // todas las pestañas.
    final SeismicEvent? officialEvent = context
        .select<SeismikState, SeismicEvent?>((s) => s.officialEvent);
    final SeismicEvent? activeAlert = context
        .select<SeismikState, SeismicEvent?>((s) => s.activeAlert);
    final SeismicEvent? latestEvent = context
        .select<SeismikState, SeismicEvent?>(
          (s) => s.recentEvents.isEmpty ? null : s.recentEvents.first,
        );
    final SeismikState state = Provider.of<SeismikState>(
      context,
      listen: false,
    );
    if (officialEvent != null) {
      return EventDetailScreen(
        event: officialEvent,
        onClose: state.clearOfficialEvent,
      );
    }
    final SeismicEvent? event = latestEvent;
    final Widget tabs = CupertinoTabScaffold(
      tabBar: CupertinoTabBar(
        // Un color translúcido activa el material del sistema en la barra: el
        // mapa se difumina debajo en lugar de quedar cortado por una franja
        // opaca. Con alfa 1.0 iOS dibujaría una barra sólida.
        backgroundColor: CupertinoColors.systemBackground
            .resolveFrom(context)
            .withValues(alpha: 0.72),
        items: <BottomNavigationBarItem>[
          BottomNavigationBarItem(
            icon: Icon(CupertinoIcons.clock),
            label: 'Historial',
          ),
          BottomNavigationBarItem(
            icon: Icon(CupertinoIcons.waveform_path_ecg),
            label: 'Sismo sentido',
          ),
          BottomNavigationBarItem(
            icon: Icon(CupertinoIcons.house_alt),
            label: 'Daños',
          ),
          BottomNavigationBarItem(
            icon: Icon(CupertinoIcons.gear_alt),
            label: 'Configuración',
          ),
        ],
      ),
      tabBuilder: (context, index) => CupertinoTabView(
        builder: (_) => switch (index) {
          0 => const MonitorScreen(),
          1 => FeltReportScreen(event: event),
          2 => DamageReportScreen(event: event),
          _ => IosSettingsScreen(
            dynamicColorAvailable: dynamicColorAvailable,
          ),
        },
      ),
    );
    if (activeAlert == null) return tabs;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        tabs,
        Material(
          child: AlertOverlay(
            event: activeAlert,
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
          height: 72,
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
