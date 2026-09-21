import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:seismik_shared/felt_area.dart';

import 'api.dart';
import 'event.dart';
import 'family.dart';
import 'family_screen.dart';
import 'rotary.dart';
import 'theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp();
    await FirebaseAppCheck.instance.activate(
      providerAndroid: kReleaseMode
          ? const AndroidPlayIntegrityProvider()
          : const AndroidDebugProvider(),
    );
  } on Object {
    // Sin App Check la app abre igual: el registro lo explicará al fallar.
  }
  runApp(const SeismikWearApp());
}

class SeismikWearApp extends StatelessWidget {
  const SeismikWearApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Seismik',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: wearBackground,
      colorScheme: const ColorScheme.dark(
        surface: wearBackground,
        primary: wearPrimary,
      ),
      fontFamily: 'Roboto',
    ),
    home: const WatchHome(),
  );
}

class WatchHome extends StatefulWidget {
  const WatchHome({super.key});

  @override
  State<WatchHome> createState() => _WatchHomeState();
}

class _WatchHomeState extends State<WatchHome> {
  final SeismikWearApi _api = SeismikWearApi();
  final WearFamily _family = WearFamily();
  final ScrollController _scroll = ScrollController();
  List<WearEvent> _events = <WearEvent>[];
  Position? _position;
  bool _loading = true;
  bool _offline = false;
  String? _error;
  Timer? _clock;

  @override
  void initState() {
    super.initState();
    unawaited(_refresh());
    // La antigüedad («hace 4 min») envejece sola mientras la pantalla está viva.
    _clock = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _clock?.cancel();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    // La ubicación mejora el registro y permite estimar la sacudida, pero no
    // puede retrasar la consulta: se pide en paralelo y la pantalla se
    // recalcula sola cuando llega.
    final Future<void> locating = _locate();
    await Future.any(<Future<void>>[
      locating,
      Future<void>.delayed(const Duration(seconds: 3)),
    ]);
    try {
      final List<WearEvent> events = await _api.recentEvents(
        latitude: _position?.latitude,
        longitude: _position?.longitude,
      );
      if (!mounted) return;
      setState(() {
        _events = events;
        _offline = false;
        _loading = false;
      });
    } on Object catch (error) {
      final List<WearEvent> cached = await _api.cachedEvents();
      if (!mounted) return;
      setState(() {
        // Lo guardado se muestra marcado como viejo: nunca como si fuera nuevo.
        _events = cached;
        _offline = true;
        _error = cached.isEmpty ? '$error' : null;
        _loading = false;
      });
    }
  }

  Future<void> _locate() async {
    try {
      LocationPermission permission = await Geolocator.checkPermission();
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
      }
      if (permission == LocationPermission.denied ||
          permission == LocationPermission.deniedForever) {
        return;
      }
      // La última conocida llega al instante; el GPS de un reloj bajo techo
      // puede tardar medio minuto en fijar posición.
      final Position? known = await Geolocator.getLastKnownPosition();
      if (known != null && mounted) setState(() => _position = known);
      final Position position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 25),
        ),
      );
      if (mounted) setState(() => _position = position);
    } on Object {
      // Sin ubicación se muestra el sismo igual, sólo que sin «aquí».
    }
  }

  @override
  Widget build(BuildContext context) {
    final WearEvent? latest = headlineEvent(
      _events,
      latitude: _position?.latitude,
      longitude: _position?.longitude,
    );
    return Scaffold(
      body: SafeArea(
        child: RotaryScroll(
          controller: _scroll,
          child: RefreshIndicator(
            onRefresh: _refresh,
            backgroundColor: wearSurface,
            child: ListView(
              controller: _scroll,
              // Margen generoso: en una pantalla redonda las esquinas se pierden.
              padding: const EdgeInsets.fromLTRB(20, 10, 20, 28),
              children: <Widget>[
                _Header(offline: _offline, loading: _loading),
                if (_error != null)
                  _Message(text: _error!)
                else if (latest == null && !_loading)
                  const _Message(text: 'Sin sismos recientes.')
                else if (latest != null) ...<Widget>[
                  HeroCard(event: latest, position: _position),
                  const SizedBox(height: 14),
                  for (final WearEvent event in _events.skip(1).take(6))
                    _EventRow(event: event, position: _position),
                ],
                const SizedBox(height: 10),
                SizedBox(
                  height: 44,
                  child: FilledButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (BuildContext context) =>
                            FamilyScreen(family: _family, eventId: latest?.id),
                      ),
                    ),
                    style: FilledButton.styleFrom(
                      backgroundColor: wearSurface,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(22),
                      ),
                    ),
                    child: const Text(
                      'Familia',
                      style: TextStyle(
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ),
                Center(
                  child: TextButton(
                    onPressed: _loading ? null : _refresh,
                    child: const Text('Actualizar'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _Header extends StatelessWidget {
  const _Header({required this.offline, required this.loading});

  final bool offline;
  final bool loading;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.only(bottom: 10),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: <Widget>[
        Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: loading
                ? const Color(0xFF7CC4FF)
                : offline
                ? const Color(0xFFFBBF24)
                : const Color(0xFF4ADE80),
          ),
        ),
        const SizedBox(width: 8),
        Text(
          loading
              ? 'Actualizando'
              : offline
              ? 'Sin conexión'
              : 'SEISMIK',
          style: const TextStyle(
            color: wearMuted,
            fontSize: 11,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.4,
          ),
        ),
      ],
    ),
  );
}

class _Message extends StatelessWidget {
  const _Message({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Padding(
    padding: const EdgeInsets.symmetric(vertical: 24),
    child: Text(
      text,
      textAlign: TextAlign.center,
      style: const TextStyle(color: wearMuted, fontSize: 13, height: 1.4),
    ),
  );
}

/// El último sismo: lo que una persona quiere ver de un vistazo.
///
/// Cabe entera en una pantalla de reloj (426 px): sin desplazarse se lee la
/// magnitud, el lugar, cuándo fue y cuánto sacudió donde estás.
class HeroCard extends StatelessWidget {
  const HeroCard({required this.event, required this.position, super.key});

  final WearEvent event;
  final Position? position;

  @override
  Widget build(BuildContext context) {
    final double? intensity = event.intensityAt(
      position?.latitude,
      position?.longitude,
    );
    final double? distance = event.distanceKmFrom(
      position?.latitude,
      position?.longitude,
    );
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 14),
      decoration: BoxDecoration(
        color: wearSurface,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: magnitudeColor(event).withValues(alpha: 0.5)),
      ),
      child: Column(
        // Sólo lo que ocupa su contenido: dentro de una lista da igual, pero
        // en cualquier otro sitio la tarjeta se estiraría a toda la pantalla.
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: <Widget>[
              Text(
                event.magnitudeLabel,
                style: TextStyle(
                  color: magnitudeColor(event),
                  fontSize: 34,
                  height: 1,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -1.2,
                ),
              ),
              if (event.preliminary) ...<Widget>[
                const SizedBox(width: 8),
                const Text(
                  'preliminar',
                  style: TextStyle(color: wearMuted, fontSize: 10),
                ),
              ],
            ],
          ),
          const SizedBox(height: 6),
          Text(
            event.place ?? 'Ubicación por confirmar',
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 13,
              height: 1.2,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            event.ago(),
            style: const TextStyle(color: wearMuted, fontSize: 11),
          ),
          const SizedBox(height: 8),
          _ShakingLine(
            intensity: intensity,
            distanceKm: distance,
            located: position != null,
          ),
        ],
      ),
    );
  }
}

/// Una sola línea: lo que se sintió aquí, o por qué todavía no se sabe.
class _ShakingLine extends StatelessWidget {
  const _ShakingLine({
    required this.intensity,
    required this.distanceKm,
    required this.located,
  });

  final double? intensity;
  final double? distanceKm;
  final bool located;

  @override
  Widget build(BuildContext context) {
    final double? intensity = this.intensity;
    if (intensity == null) {
      return Text(
        located ? 'Sin epicentro para estimar' : 'Buscando tu ubicación…',
        textAlign: TextAlign.center,
        style: const TextStyle(color: wearMuted, fontSize: 11),
      );
    }
    final String far = distanceKm == null ? '' : ' · a ${_km(distanceKm!)}';
    if (intensity < feltIntensity) {
      return Text(
        'No se sintió aquí$far',
        textAlign: TextAlign.center,
        maxLines: 2,
        style: const TextStyle(color: wearMuted, fontSize: 11, height: 1.3),
      );
    }
    final Color color = intensityColor(intensity);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.6)),
      ),
      child: Text(
        'Aquí ${intensityRoman(intensity)} · ${intensityName(intensity)}$far',
        textAlign: TextAlign.center,
        maxLines: 2,
        style: TextStyle(
          color: color,
          fontSize: 11,
          height: 1.3,
          fontWeight: FontWeight.w800,
        ),
      ),
    );
  }
}

/// «4.259 km», con el punto de miles que se usa en español.
String _km(double kilometres) {
  final int rounded = kilometres.round();
  if (rounded < 1000) return '$rounded km';
  final String digits = '$rounded';
  final String head = digits.substring(0, digits.length - 3);
  return '$head.${digits.substring(digits.length - 3)} km';
}

class _EventRow extends StatelessWidget {
  const _EventRow({required this.event, required this.position});

  final WearEvent event;
  final Position? position;

  @override
  Widget build(BuildContext context) {
    final double? intensity = event.intensityAt(
      position?.latitude,
      position?.longitude,
    );
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: wearSurface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: <Widget>[
          SizedBox(
            width: 38,
            child: Text(
              event.magnitudeLabel,
              style: TextStyle(
                color: magnitudeColor(event),
                fontSize: 17,
                fontWeight: FontWeight.w800,
              ),
            ),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  event.place ?? 'Sin ubicar',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
                Text(
                  intensity == null
                      ? event.ago()
                      : '${event.ago()} · aquí ${intensityRoman(intensity)}',
                  style: const TextStyle(color: wearMuted, fontSize: 11),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// Mismos colores que la app de teléfono para la magnitud.
Color magnitudeColor(WearEvent event) {
  if (event.preliminary && event.magnitude == null) {
    return const Color(0xFFBF5AF2);
  }
  final double? magnitude = event.magnitude;
  if (magnitude == null) return wearMuted;
  if (magnitude < 3.5) return const Color(0xFF30D158);
  if (magnitude < 4.8) return const Color(0xFF32ADE6);
  if (magnitude < 6.0) return const Color(0xFFFF9F0A);
  return const Color(0xFFFF453A);
}

/// Misma escala de sacudida que el perímetro del mapa.
Color intensityColor(double intensity) {
  if (intensity >= severeIntensity) return const Color(0xFF8E0012);
  if (intensity >= strongIntensity) return const Color(0xFFE53935);
  if (intensity >= lightIntensity) return const Color(0xFFFB8C00);
  return const Color(0xFFFFB300);
}
