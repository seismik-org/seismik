import 'dart:async';

import 'package:firebase_app_check/firebase_app_check.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';
import 'package:seismik_shared/felt_area.dart';

import 'api.dart';
import 'event.dart';

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

/// Fondo negro puro: en la pantalla OLED de un reloj, cada píxel negro está
/// apagado y no gasta batería.
const Color _background = Color(0xFF000000);
const Color _surface = Color(0xFF14181F);
const Color _muted = Color(0xFF9DADC8);

class SeismikWearApp extends StatelessWidget {
  const SeismikWearApp({super.key});

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'Seismik',
    debugShowCheckedModeBanner: false,
    theme: ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: _background,
      colorScheme: const ColorScheme.dark(
        surface: _background,
        primary: Color(0xFF7CC4FF),
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
    super.dispose();
  }

  Future<void> _refresh() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    unawaited(_locate());
    try {
      final List<WearEvent> events = await _api.recentEvents();
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
      final Position position = await Geolocator.getCurrentPosition(
        locationSettings: const LocationSettings(
          accuracy: LocationAccuracy.medium,
          timeLimit: Duration(seconds: 20),
        ),
      );
      if (mounted) setState(() => _position = position);
    } on Object {
      // Sin ubicación se muestra el sismo igual, sólo que sin «aquí».
    }
  }

  @override
  Widget build(BuildContext context) {
    final WearEvent? latest = _events.isEmpty ? null : _events.first;
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          onRefresh: _refresh,
          backgroundColor: _surface,
          child: ListView(
            // Margen generoso: en una pantalla redonda las esquinas se pierden.
            padding: const EdgeInsets.fromLTRB(20, 10, 20, 28),
            children: <Widget>[
              _Header(offline: _offline, loading: _loading),
              if (_error != null)
                _Message(text: _error!)
              else if (latest == null && !_loading)
                const _Message(text: 'Sin sismos recientes.')
              else if (latest != null) ...<Widget>[
                _LatestCard(event: latest, position: _position),
                const SizedBox(height: 14),
                for (final WearEvent event in _events.skip(1).take(6))
                  _EventRow(event: event, position: _position),
              ],
              const SizedBox(height: 10),
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
            color: _muted,
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
      style: const TextStyle(color: _muted, fontSize: 13, height: 1.4),
    ),
  );
}

/// El último sismo: lo que una persona quiere ver de un vistazo.
class _LatestCard extends StatelessWidget {
  const _LatestCard({required this.event, required this.position});

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
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      decoration: BoxDecoration(
        color: _surface,
        borderRadius: BorderRadius.circular(22),
        border: Border.all(color: magnitudeColor(event).withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: <Widget>[
          Text(
            event.magnitudeLabel,
            style: TextStyle(
              color: magnitudeColor(event),
              fontSize: 40,
              height: 1,
              fontWeight: FontWeight.w900,
              letterSpacing: -1.5,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            event.preliminary ? 'preliminar' : 'magnitud',
            style: const TextStyle(color: _muted, fontSize: 11),
          ),
          const SizedBox(height: 10),
          Text(
            event.place ?? 'Ubicación por confirmar',
            textAlign: TextAlign.center,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 14,
              height: 1.25,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            event.ago(),
            style: const TextStyle(color: _muted, fontSize: 12),
          ),
          if (intensity != null) ...<Widget>[
            const SizedBox(height: 12),
            _IntensityBadge(intensity: intensity, distanceKm: distance),
          ],
        ],
      ),
    );
  }
}

/// Lo que se sintió donde está la persona, con la escala de la app.
class _IntensityBadge extends StatelessWidget {
  const _IntensityBadge({required this.intensity, required this.distanceKm});

  final double intensity;
  final double? distanceKm;

  @override
  Widget build(BuildContext context) {
    final Color color = intensityColor(intensity);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: color.withValues(alpha: 0.6)),
      ),
      child: Column(
        children: <Widget>[
          Text(
            'Aquí: ${intensityRoman(intensity)} · ${intensityName(intensity)}',
            textAlign: TextAlign.center,
            style: TextStyle(
              color: color,
              fontSize: 12,
              fontWeight: FontWeight.w800,
            ),
          ),
          if (distanceKm != null)
            Text(
              'a ${distanceKm!.round()} km',
              style: const TextStyle(color: _muted, fontSize: 11),
            ),
        ],
      ),
    );
  }
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
        color: _surface,
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
                  style: const TextStyle(color: _muted, fontSize: 11),
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
  if (magnitude == null) return _muted;
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
