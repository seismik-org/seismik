import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models/seismic_event.dart';
import '../../services/emergency_store.dart';
import '../../state/seismik_state.dart';
import 'event_detail_screen.dart';
import 'felt_report_screen.dart';
import 'government_sources_screen.dart';

/// Guía de emergencia que funciona sin red ni sesión. Se enciende sola cuando
/// el teléfono pierde la señal y se apaga sola cuando vuelve; también se puede
/// abrir desde Configuración y dejar fija.
class OfflineEmergencyScreen extends StatefulWidget {
  const OfflineEmergencyScreen({super.key});

  @override
  State<OfflineEmergencyScreen> createState() => _OfflineEmergencyScreenState();
}

class _OfflineEmergencyScreenState extends State<OfflineEmergencyScreen> {
  static const int _notesLimit = 1000;
  final TextEditingController _notes = TextEditingController();
  DateTime? _cachedAt;
  List<SeismicEvent> _cached = <SeismicEvent>[];
  bool _syncing = false;
  String? _syncMessage;

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

  Future<void> _retry(SeismikState state) async {
    setState(() {
      _syncing = true;
      _syncMessage = null;
    });
    final bool connected = await state.retryConnection();
    await _load();
    if (!mounted) return;
    setState(() {
      _syncing = false;
      _syncMessage = connected
          ? 'Sincronizado con la señal disponible.'
          : 'Sigue sin haber señal. Lo intentamos solos en cuanto vuelva.';
    });
  }

  @override
  Widget build(BuildContext context) {
    final SeismikState state = context.watch<SeismikState>();
    final ThemeData theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('Modo de emergencia')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
        children: <Widget>[
          _statusCard(state, theme),
          const SizedBox(height: 12),
          _shakingCard(theme),
          const SizedBox(height: 12),
          _afterCard(theme),
          const SizedBox(height: 12),
          _meetingCard(theme),
          const SizedBox(height: 12),
          _reportsCard(state, theme),
          const SizedBox(height: 12),
          _savedQuakesCard(theme),
          const SizedBox(height: 12),
          _optionsCard(state, theme),
          const SizedBox(height: 20),
          _footer(theme),
        ],
      ),
    );
  }

  // --- tarjetas -------------------------------------------------------------

  Widget _statusCard(SeismikState state, ThemeData theme) {
    final bool active = state.offlineEmergencyMode;
    final Color tint = state.hasSignal
        ? (active ? Colors.amber.shade800 : Colors.green.shade700)
        : theme.colorScheme.error;
    final String text = !state.hasSignal
        ? 'El modo de emergencia está activo. Usa la guía y tus notas de abajo. '
              'Los reportes quedan en cola y salen solos cuando vuelva la señal.'
        : active
        ? 'Seguirá activo aunque haya señal, porque lo fijaste. Puedes apagarlo '
              'al final de esta pantalla.'
        : 'Se activa solo si pierdes la señal y se apaga solo cuando vuelve.';
    return _Panel(
      title: state.hasSignal
          ? (active ? 'Modo de emergencia fijado' : 'Hay señal')
          : 'Sin señal',
      icon: state.hasSignal
          ? (active ? Icons.bolt_rounded : Icons.signal_cellular_alt_rounded)
          : Icons.signal_wifi_off,
      tint: tint,
      children: <Widget>[
        Text(text),
        Text(
          'Sin red no llegan sismos nuevos ni se actualiza la ubicación de tu '
          'familia. Lo guardado en el teléfono no confirma que alguien esté a salvo.',
          style: theme.textTheme.bodySmall,
        ),
        FilledButton.icon(
          onPressed: _syncing ? null : () => _retry(state),
          icon: _syncing
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.sync),
          label: Text(
            _syncing ? 'Buscando señal…' : 'Buscar señal y sincronizar',
          ),
        ),
        if (_syncMessage != null)
          Text(_syncMessage!, style: theme.textTheme.bodySmall),
      ],
    );
  }

  Widget _shakingCard(ThemeData theme) => _Panel(
    title: 'Si está temblando',
    icon: Icons.warning_amber_rounded,
    tint: theme.colorScheme.error,
    children: <Widget>[
      const _Step(
        1,
        'Agáchate',
        'Ponte de rodillas y protege tu cabeza y tu cuello.',
      ),
      const _Step(
        2,
        'Cúbrete',
        'Métete bajo una mesa sólida o pégate a un muro interior.',
      ),
      const _Step(3, 'Sujétate', 'Quédate así hasta que pare la sacudida.'),
      Text(
        'Aléjate de ventanas y de objetos que puedan caer. No uses ascensores.',
        style: theme.textTheme.bodySmall,
      ),
    ],
  );

  Widget _afterCard(ThemeData theme) => _Panel(
    title: 'Cuando pare',
    icon: Icons.health_and_safety_outlined,
    tint: Colors.green.shade700,
    children: const <Widget>[
      _Bullet(
        'Revisa si hay personas heridas y pide ayuda: en Colombia, llama al 123.',
      ),
      _Bullet(
        'Prepárate para réplicas: vuelve a agacharte, cubrirte y sujetarte.',
      ),
      _Bullet(
        'Si hueles gas o ves daños, sal con cuidado y aléjate del edificio.',
      ),
      _Bullet(
        'Escribe mensajes de texto y deja las llamadas libres para las emergencias.',
      ),
    ],
  );

  Widget _meetingCard(ThemeData theme) => _Panel(
    title: 'Punto de encuentro y notas',
    icon: Icons.place_outlined,
    tint: theme.colorScheme.primary,
    children: <Widget>[
      TextField(
        controller: _notes,
        maxLength: _notesLimit,
        maxLines: 4,
        decoration: const InputDecoration(
          border: OutlineInputBorder(),
          hintText: 'Dónde se reúne tu familia, teléfonos, medicinas…',
          helperText:
              'Se guardan sólo en este teléfono; no se envían a Seismik ni a tu familia.',
          helperMaxLines: 2,
        ),
        onChanged: (String value) => EmergencyStore.saveNotes(value),
      ),
    ],
  );

  Widget _reportsCard(SeismikState state, ThemeData theme) {
    final int pending = state.pendingReportCount;
    final String text = switch (pending) {
      0 => 'No tienes reportes pendientes.',
      1 => '1 reporte pendiente. Aún no se ha entregado.',
      _ => '$pending reportes pendientes. Aún no se han entregado.',
    };
    return _Panel(
      title: 'Reportes',
      icon: Icons.edit_note,
      tint: Colors.amber.shade800,
      children: <Widget>[
        Text(text),
        OutlinedButton.icon(
          onPressed: () => Navigator.of(context).push(
            MaterialPageRoute<void>(builder: (_) => const FeltReportScreen()),
          ),
          icon: const Icon(Icons.vibration),
          label: const Text('Preparar un reporte «Lo sentí»'),
        ),
        Text(
          'Sin señal queda guardado en el teléfono y no se entrega hasta que vuelva.',
          style: theme.textTheme.bodySmall,
        ),
      ],
    );
  }

  Widget _savedQuakesCard(ThemeData theme) => _Panel(
    title: 'Últimos sismos guardados',
    icon: Icons.history,
    tint: Colors.lightBlue.shade700,
    children: <Widget>[
      if (_cachedAt != null)
        Text(
          'Copia del ${_cachedAt!.toLocal().toString().split('.').first}. No son datos en vivo.',
          style: theme.textTheme.bodySmall,
        ),
      if (_cached.isEmpty)
        const Text(
          'Todavía no hay sismos guardados. La guía y las notas funcionan igual sin red.',
        ),
      for (final SeismicEvent event in _cached.take(8))
        InkWell(
          onTap: () => Navigator.of(context).push(
            MaterialPageRoute<void>(
              builder: (_) => EventDetailScreen(event: event),
            ),
          ),
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                SizedBox(
                  width: 60,
                  child: Text(
                    event.magnitude == null
                        ? 'M —'
                        : 'M ${event.magnitude!.toStringAsFixed(1)}',
                    style: const TextStyle(fontWeight: FontWeight.w700),
                  ),
                ),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(event.displayPlace ?? 'Epicentro en revisión'),
                      Text(
                        event.detectedAt.toLocal().toString().split('.').first,
                        style: theme.textTheme.bodySmall,
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
    ],
  );

  Widget _optionsCard(SeismikState state, ThemeData theme) => _Panel(
    title: 'Opciones',
    icon: Icons.tune,
    tint: theme.colorScheme.outline,
    children: <Widget>[
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: const Text('Mantener activo aunque haya señal'),
        subtitle: const Text(
          'Útil si la señal es tan débil que nada carga. No apaga las alertas: '
          'seguirás recibiéndolas cuando haya red.',
        ),
        value: state.emergencyPinned,
        onChanged: state.setEmergencyPinned,
      ),
    ],
  );

  Widget _footer(ThemeData theme) => Column(
    children: <Widget>[
      Text(
        'Guía basada en las recomendaciones de los CDC. Seismik es independiente '
        'y no representa a ninguna entidad pública.',
        textAlign: TextAlign.center,
        style: theme.textTheme.bodySmall,
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
    ],
  );
}

class _Panel extends StatelessWidget {
  const _Panel({
    required this.title,
    required this.icon,
    required this.tint,
    required this.children,
  });

  final String title;
  final IconData icon;
  final Color tint;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Card(
      elevation: 0,
      color: theme.colorScheme.surfaceContainerHighest.withValues(alpha: 0.5),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            Row(
              children: <Widget>[
                Icon(icon, color: tint),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(title, style: theme.textTheme.titleMedium),
                ),
              ],
            ),
            for (final Widget child in children) ...<Widget>[
              const SizedBox(height: 12),
              child,
            ],
          ],
        ),
      ),
    );
  }
}

class _Step extends StatelessWidget {
  const _Step(this.number, this.title, this.detail);

  final int number;
  final String title;
  final String detail;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        CircleAvatar(
          radius: 14,
          backgroundColor: theme.colorScheme.error,
          foregroundColor: theme.colorScheme.onError,
          child: Text(
            '$number',
            style: const TextStyle(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(title, style: theme.textTheme.titleLarge),
              Text(detail, style: theme.textTheme.bodyMedium),
            ],
          ),
        ),
      ],
    );
  }
}

class _Bullet extends StatelessWidget {
  const _Bullet(this.text);

  final String text;

  @override
  Widget build(BuildContext context) => Row(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      const Text('•  ', style: TextStyle(fontWeight: FontWeight.w700)),
      Expanded(child: Text(text)),
    ],
  );
}
