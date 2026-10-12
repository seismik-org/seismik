import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/seismic_event.dart';
import '../../services/emergency_store.dart';
import '../../state/seismik_state.dart';
import 'event_detail_screen.dart';
import 'felt_report_screen.dart';
import 'government_sources_screen.dart';

class OfflineEmergencyScreen extends StatefulWidget {
  const OfflineEmergencyScreen({super.key});
  @override
  State<OfflineEmergencyScreen> createState() => _OfflineEmergencyScreenState();
}

class _OfflineEmergencyScreenState extends State<OfflineEmergencyScreen> {
  final TextEditingController _notes = TextEditingController();
  DateTime? _cachedAt;
  List<SeismicEvent> _cached = <SeismicEvent>[];
  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final SeismikState state = context.read<SeismikState>();
    final String notes = await EmergencyStore.notes();
    final DateTime? date = await EmergencyStore.cachedAt();
    final List<SeismicEvent> events = await state.api.readCachedEvents();
    if (!mounted) return;
    setState(() {
      _notes.text = notes;
      _cachedAt = date;
      _cached = events;
    });
  }

  @override
  void dispose() {
    _notes.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    return Scaffold(
      appBar: AppBar(title: const Text('Modo de emergencia')),
      body: ListView(
        padding: const EdgeInsets.all(20),
        children: <Widget>[
          const Text(
            'Disponible sin conexión ni inicio de sesión',
            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18),
          ),
          const SizedBox(height: 12),
          const Text(
            'Sin red no recibes sismos nuevos ni se actualiza la ubicación de tu familia. '
            'Los datos guardados no confirman que alguien esté a salvo.',
          ),
          SwitchListTile(
            title: const Text('Usar datos guardados'),
            subtitle: const Text(
              'Pospone descargas y envíos. No desactiva las alertas push si vuelve la red.',
            ),
            value: state.offlineEmergencyMode,
            onChanged: state.setOfflineEmergencyMode,
          ),
          Text(
            'Última copia descargada: ${_cachedAt?.toLocal().toString().split('.').first ?? 'Todavía no hay una copia'}',
          ),
          Text(
            '${state.pendingReportCount} reportes pendientes; no se han entregado.',
          ),
          FilledButton.icon(
            onPressed: () async {
              await state.setOfflineEmergencyMode(false);
              await state.refreshNetworkData();
              await _load();
            },
            icon: const Icon(Icons.sync),
            label: const Text('Buscar conexión y sincronizar'),
          ),
          const Divider(height: 32),
          const Text(
            'Durante la sacudida, dentro de un edificio',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          const Text(
            'Agáchate, protege cabeza y cuello bajo una mesa sólida y sujétate hasta que pare la sacudida. '
            'Aléjate de ventanas y objetos que puedan caer.',
          ),
          const Text(
            'Guía guardada de CDC · Seismik es independiente y no representa a una entidad pública.',
          ),
          TextButton(
            onPressed: () => launchUrl(
              Uri.parse('https://www.cdc.gov/earthquakes/safety/index.html'),
            ),
            child: const Text('Fuente de la guía (necesita conexión)'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => const GovernmentSourcesScreen(),
              ),
            ),
            child: const Text('Fuentes y aviso legal'),
          ),
          const Divider(height: 32),
          TextField(
            controller: _notes,
            maxLength: 1000,
            maxLines: 4,
            decoration: const InputDecoration(
              labelText: 'Punto de encuentro y notas',
              helperText:
                  'Sólo en este teléfono. No se envían automáticamente.',
            ),
          ),
          OutlinedButton(
            onPressed: () async {
              await EmergencyStore.saveNotes(_notes.text);
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Notas guardadas en este teléfono.'),
                  ),
                );
              }
            },
            child: const Text('Guardar notas locales'),
          ),
          ListTile(
            leading: const Icon(Icons.edit_note),
            title: const Text('Preparar un reporte'),
            subtitle: const Text(
              'Selecciona un sismo conocido. Sin conexión queda pendiente, no enviado.',
            ),
            onTap: () => Navigator.of(context).push(
              MaterialPageRoute<void>(builder: (_) => const FeltReportScreen()),
            ),
          ),
          const Divider(height: 32),
          const Text(
            'Sismos guardados · no son datos en vivo',
            style: TextStyle(fontWeight: FontWeight.bold),
          ),
          if (_cached.isEmpty)
            const Text(
              'Aún no hay sismos descargados. La guía y las notas sí funcionan sin red.',
            ),
          for (final SeismicEvent event in _cached.take(20))
            ListTile(
              title: Text(event.displayPlace ?? 'Epicentro en revisión'),
              subtitle: Text(
                '${event.detectedAt.toLocal()} · M ${event.magnitude ?? '—'}',
              ),
              onTap: () => Navigator.of(context).push(
                MaterialPageRoute<void>(
                  builder: (_) => EventDetailScreen(event: event),
                ),
              ),
            ),
        ],
      ),
    );
  }
}
