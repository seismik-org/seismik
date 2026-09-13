import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../data/models/family_circle.dart';
import '../../data/models/seismic_event.dart';
import '../../state/family_state.dart';

/// Búsqueda de familiares.
///
/// Tras un sismo cada integrante avisa si está bien o necesita ayuda. Ese toque
/// comparte su ubicación con el círculo durante unas horas y avisa a los demás.
/// Nada se comparte sin que la persona toque un botón.
class FamilySafetyScreen extends StatelessWidget {
  const FamilySafetyScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final FamilyState family = context.watch<FamilyState>();
    final FamilyCircle? circle = family.circle;
    final Widget body;
    if (family.account == null) {
      body = _SignInPrompt(family: family);
    } else if (circle == null && family.loading) {
      body = const Center(child: CircularProgressIndicator());
    } else if (circle == null) {
      body = _NoCircle(family: family);
    } else {
      body = _CircleView(family: family, circle: circle);
    }
    return Scaffold(
      appBar: AppBar(
        title: const Text('Familia'),
        actions: <Widget>[
          if (family.account != null) ...<Widget>[
            IconButton(
              tooltip: 'Actualizar',
              onPressed: family.refresh,
              icon: const Icon(Icons.refresh_rounded),
            ),
            PopupMenuButton<String>(
              tooltip: 'Cuenta',
              onSelected: (_) => unawaited(family.signOut()),
              itemBuilder: (context) => <PopupMenuEntry<String>>[
                PopupMenuItem<String>(
                  value: 'signout',
                  child: Text('Cerrar sesión · ${family.account!.email}'),
                ),
              ],
            ),
          ],
        ],
      ),
      body: body,
    );
  }
}

class _SignInPrompt extends StatelessWidget {
  const _SignInPrompt({required this.family});

  final FamilyState family;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 120),
      children: <Widget>[
        Icon(
          Icons.family_restroom_rounded,
          size: 64,
          color: theme.colorScheme.primary,
        ),
        const SizedBox(height: 16),
        Text(
          'Avísale a tu familia que estás bien',
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 12),
        const Text(
          'Tras un sismo, cada integrante de tu círculo reporta si está bien o '
          'necesita ayuda. Ese reporte comparte su ubicación con la familia '
          'durante unas horas y les llega como notificación.',
        ),
        const SizedBox(height: 12),
        Text(
          'Para saber quién es quién necesitas iniciar sesión. Seismik nunca '
          'comparte tu ubicación sin que toques un botón.',
          style: theme.textTheme.bodySmall,
        ),
        if (family.error != null)
          Padding(
            padding: const EdgeInsets.only(top: 16),
            child: Text(
              family.error!,
              style: TextStyle(color: theme.colorScheme.error),
            ),
          ),
        const SizedBox(height: 28),
        FilledButton.icon(
          style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
          onPressed: family.signingIn ? null : () => family.signIn(),
          icon: family.signingIn
              ? const SizedBox.square(
                  dimension: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.login_rounded),
          label: Text(
            family.signingIn
                ? 'Esperando a Google…'
                : 'Iniciar sesión con Google',
          ),
        ),
      ],
    );
  }
}

class _NoCircle extends StatelessWidget {
  const _NoCircle({required this.family});

  final FamilyState family;

  Future<void> _create(BuildContext context) async {
    final List<String>? values = await showDialog<List<String>>(
      context: context,
      builder: (_) => _FieldsDialog(
        title: 'Crear círculo familiar',
        action: 'Crear',
        fields: <(String, String)>[
          ('Cómo te verá tu familia', family.account?.firstName ?? ''),
          ('Nombre del círculo', 'Mi familia'),
        ],
      ),
    );
    if (values == null) return;
    try {
      await family.createCircle(displayName: values[0], circleName: values[1]);
    } catch (_) {
      if (context.mounted) {
        _snack(context, 'No se pudo crear el círculo. Inténtalo otra vez.');
      }
    }
  }

  Future<void> _join(BuildContext context) async {
    final List<String>? values = await showDialog<List<String>>(
      context: context,
      builder: (_) => _FieldsDialog(
        title: 'Unirme a un círculo',
        action: 'Unirme',
        fields: <(String, String)>[
          ('Código de invitación', ''),
          ('Cómo te verá tu familia', family.account?.firstName ?? ''),
        ],
      ),
    );
    if (values == null) return;
    try {
      await family.joinCircle(inviteCode: values[0], displayName: values[1]);
    } catch (_) {
      if (context.mounted) {
        _snack(
          context,
          'El código no es válido, ya venció o tu cuenta ya está en un círculo.',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    return ListView(
      padding: const EdgeInsets.fromLTRB(24, 24, 24, 120),
      children: <Widget>[
        Text(
          'Hola, ${family.account?.firstName ?? ''}',
          style: theme.textTheme.headlineSmall?.copyWith(
            fontWeight: FontWeight.w800,
          ),
        ),
        const SizedBox(height: 8),
        const Text(
          'Crea el círculo de tu familia o únete con el código que te envió '
          'quien lo creó. Cada código sirve una sola vez y vence en 24 horas.',
        ),
        if (family.error != null)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              family.error!,
              style: TextStyle(color: theme.colorScheme.error),
            ),
          ),
        const SizedBox(height: 28),
        FilledButton.icon(
          style: FilledButton.styleFrom(minimumSize: const Size.fromHeight(52)),
          onPressed: () => _create(context),
          icon: const Icon(Icons.group_add_outlined),
          label: const Text('Crear mi círculo'),
        ),
        const SizedBox(height: 10),
        OutlinedButton(
          style: OutlinedButton.styleFrom(
            minimumSize: const Size.fromHeight(52),
          ),
          onPressed: () => _join(context),
          child: const Text('Tengo un código de invitación'),
        ),
      ],
    );
  }
}

class _CircleView extends StatelessWidget {
  const _CircleView({required this.family, required this.circle});

  final FamilyState family;
  final FamilyCircle circle;

  Future<void> _invite(BuildContext context) async {
    final List<String>? values = await showDialog<List<String>>(
      context: context,
      builder: (_) => const _FieldsDialog(
        title: 'Invitar familiar',
        action: 'Crear código',
        fields: <(String, String)>[('Nombre de la persona', '')],
      ),
    );
    if (values == null || !context.mounted) return;
    try {
      final String code = await family.createInvitation(values[0]);
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => AlertDialog(
          title: const Text('Código de invitación'),
          content: SelectableText(
            '$code\n\nVence en 24 horas y sirve una sola vez. Compártelo sólo '
            'con la persona invitada.',
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: code));
                if (dialogContext.mounted) Navigator.pop(dialogContext);
              },
              child: const Text('Copiar'),
            ),
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cerrar'),
            ),
          ],
        ),
      );
    } catch (_) {
      if (context.mounted) {
        _snack(context, 'Sólo quien creó el círculo puede invitar.');
      }
    }
  }

  Future<void> _stopSharing(BuildContext context) async {
    try {
      await family.stopSharingLocation();
      if (context.mounted) {
        _snack(context, 'Tu familia ya no ve tu ubicación.');
      }
    } catch (_) {
      if (context.mounted) {
        _snack(context, 'No se pudo borrar tu ubicación. Revisa tu conexión.');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<FamilyMember> located = circle.members
        .where((member) => member.location != null)
        .toList(growable: false);
    return RefreshIndicator(
      onRefresh: family.refresh,
      child: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
        children: <Widget>[
          _CheckInCard(family: family),
          const SizedBox(height: 12),
          if (located.isNotEmpty) ...<Widget>[
            _FamilyMap(members: located),
            const SizedBox(height: 12),
          ],
          Card(
            clipBehavior: Clip.antiAlias,
            child: Column(
              children: <Widget>[
                ListTile(
                  title: Text(
                    circle.circleName,
                    style: const TextStyle(fontWeight: FontWeight.w800),
                  ),
                  subtitle: Text(
                    circle.members.length == 1
                        ? '1 integrante'
                        : '${circle.members.length} integrantes',
                  ),
                ),
                for (final FamilyMember member in circle.members)
                  _MemberTile(member: member),
              ],
            ),
          ),
          const SizedBox(height: 12),
          if (circle.isOwner)
            OutlinedButton.icon(
              onPressed: () => _invite(context),
              icon: const Icon(Icons.person_add_alt_1_outlined),
              label: const Text('Invitar familiar'),
            ),
          TextButton.icon(
            onPressed: () => _stopSharing(context),
            icon: const Icon(Icons.location_off_outlined),
            label: const Text('Dejar de compartir mi ubicación'),
          ),
          const SizedBox(height: 8),
          Text(
            'Seismik no sustituye a los servicios de emergencia. Si alguien '
            'está en peligro, llama a la línea de emergencias de tu país.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ),
    );
  }
}

class _CheckInCard extends StatefulWidget {
  const _CheckInCard({required this.family});

  final FamilyState family;

  @override
  State<_CheckInCard> createState() => _CheckInCardState();
}

class _CheckInCardState extends State<_CheckInCard> {
  bool _precise = false;

  Future<void> _report({required bool needsHelp}) async {
    try {
      final bool located = await widget.family.reportStatus(
        needsHelp: needsHelp,
        precise: _precise,
      );
      if (!mounted) return;
      _snack(
        context,
        !located
            ? 'Aviso enviado sin ubicación. Activa la ubicación para compartirla.'
            : needsHelp
            ? 'Tu familia sabe que necesitas ayuda y ve dónde estás.'
            : 'Tu familia sabe que estás bien.',
      );
    } catch (_) {
      if (mounted) {
        _snack(
          context,
          'No se pudo enviar el aviso. Revisa tu conexión e inténtalo otra vez.',
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme colors = theme.colorScheme;
    final SeismicEvent? event = widget.family.checkInEvent;
    final FamilyStatus? last = widget.family.circle?.you?.status;
    final bool busy = widget.family.reporting;
    return Card(
      color: event != null ? colors.errorContainer : colors.surfaceContainerHigh,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Text(
              event == null ? '¿Estás bien?' : 'Tras el sismo, ¿estás bien?',
              style: theme.textTheme.titleLarge?.copyWith(
                fontWeight: FontWeight.w800,
              ),
            ),
            if (event != null) Text(_eventLabel(event)),
            if (last != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text(
                  'Tu último aviso: '
                  '${last.needsHelp ? 'necesitas ayuda' : 'estás bien'} · '
                  '${_ago(last.reportedAt)}',
                  style: theme.textTheme.bodySmall,
                ),
              ),
            const SizedBox(height: 12),
            Row(
              children: <Widget>[
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: Colors.green.shade700,
                      foregroundColor: Colors.white,
                      minimumSize: const Size.fromHeight(52),
                    ),
                    onPressed: busy ? null : () => _report(needsHelp: false),
                    icon: const Icon(Icons.check_circle_rounded),
                    label: const Text('Estoy bien'),
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: FilledButton.icon(
                    style: FilledButton.styleFrom(
                      backgroundColor: colors.error,
                      foregroundColor: colors.onError,
                      minimumSize: const Size.fromHeight(52),
                    ),
                    onPressed: busy ? null : () => _report(needsHelp: true),
                    icon: const Icon(Icons.sos_rounded),
                    label: const Text('Necesito ayuda'),
                  ),
                ),
              ],
            ),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              value: _precise,
              onChanged: (value) => setState(() => _precise = value),
              title: const Text('Compartir ubicación precisa'),
              subtitle: const Text(
                'Desactivado, tu familia ve una zona aproximada.',
              ),
            ),
            Text(
              'Tu ubicación se comparte con tu familia durante 4 horas y '
              'luego se borra.',
              style: theme.textTheme.bodySmall,
            ),
          ],
        ),
      ),
    );
  }
}

class _FamilyMap extends StatelessWidget {
  const _FamilyMap({required this.members});

  final List<FamilyMember> members;

  @override
  Widget build(BuildContext context) {
    final FamilyLocation first = members.first.location!;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: SizedBox(
        height: 220,
        child: GoogleMap(
          // Modo ligero: una imagen del mapa en vez de un mapa interactivo.
          // Dentro de una lista es mucho más barato y no compite con el
          // desplazamiento, algo que en teléfonos modestos se nota.
          liteModeEnabled: true,
          initialCameraPosition: CameraPosition(
            target: LatLng(first.latitude, first.longitude),
            zoom: members.length == 1 ? 13 : 10,
          ),
          markers: <Marker>{
            for (final FamilyMember member in members)
              Marker(
                markerId: MarkerId(member.memberId),
                position: LatLng(
                  member.location!.latitude,
                  member.location!.longitude,
                ),
                infoWindow: InfoWindow(
                  title: member.displayName,
                  snippet: member.status == null
                      ? 'Sin aviso reciente'
                      : member.status!.needsHelp
                      ? 'Necesita ayuda'
                      : 'Está bien',
                ),
                icon: BitmapDescriptor.defaultMarkerWithHue(
                  member.status == null
                      ? BitmapDescriptor.hueAzure
                      : member.status!.needsHelp
                      ? BitmapDescriptor.hueRed
                      : BitmapDescriptor.hueGreen,
                ),
              ),
          },
          mapToolbarEnabled: false,
          zoomControlsEnabled: false,
        ),
      ),
    );
  }
}

class _MemberTile extends StatelessWidget {
  const _MemberTile({required this.member});

  final FamilyMember member;

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    final FamilyStatus? status = member.status;
    final Color accent = status == null
        ? colors.outline
        : status.needsHelp
        ? colors.error
        : Colors.green.shade700;
    final List<String> details = <String>[
      if (status == null)
        'Sin aviso reciente'
      else
        '${status.needsHelp ? 'Necesita ayuda' : 'Está bien'} · '
            '${_ago(status.reportedAt)}',
      if (status?.message != null) '«${status!.message}»',
      member.location == null
          ? 'No comparte ubicación'
          : member.location!.precision == 'precise'
          ? 'Ubicación precisa'
          : 'Ubicación aproximada',
    ];
    return ListTile(
      leading: CircleAvatar(
        backgroundColor: accent.withValues(alpha: 0.15),
        foregroundColor: accent,
        child: Text(member.initial),
      ),
      title: Text(
        member.isYou ? '${member.displayName} (tú)' : member.displayName,
      ),
      subtitle: Text(details.join('\n')),
      isThreeLine: details.length > 2,
      trailing: Icon(
        status == null
            ? Icons.help_outline_rounded
            : status.needsHelp
            ? Icons.sos_rounded
            : Icons.check_circle_rounded,
        color: accent,
      ),
    );
  }
}

/// Diálogo con uno o varios campos de texto obligatorios.
class _FieldsDialog extends StatefulWidget {
  const _FieldsDialog({
    required this.title,
    required this.action,
    required this.fields,
  });

  final String title;
  final String action;

  /// Etiqueta y valor inicial de cada campo.
  final List<(String, String)> fields;

  @override
  State<_FieldsDialog> createState() => _FieldsDialogState();
}

class _FieldsDialogState extends State<_FieldsDialog> {
  late final List<TextEditingController> _controllers =
      <TextEditingController>[
        for (final (String, String) field in widget.fields)
          TextEditingController(text: field.$2),
      ];

  @override
  void dispose() {
    for (final TextEditingController controller in _controllers) {
      controller.dispose();
    }
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => AlertDialog(
    title: Text(widget.title),
    content: Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        for (int index = 0; index < widget.fields.length; index++)
          TextField(
            controller: _controllers[index],
            decoration: InputDecoration(labelText: widget.fields[index].$1),
          ),
      ],
    ),
    actions: <Widget>[
      TextButton(
        onPressed: () => Navigator.pop(context),
        child: const Text('Cancelar'),
      ),
      FilledButton(
        onPressed: () {
          final List<String> values = <String>[
            for (final TextEditingController controller in _controllers)
              controller.text.trim(),
          ];
          if (values.any((value) => value.isEmpty)) return;
          Navigator.pop(context, values);
        },
        child: Text(widget.action),
      ),
    ],
  );
}

void _snack(BuildContext context, String message) => ScaffoldMessenger.of(
  context,
).showSnackBar(SnackBar(content: Text(message)));

String _ago(DateTime? at) {
  if (at == null) return 'hace un momento';
  final Duration elapsed = DateTime.now().toUtc().difference(at.toUtc());
  if (elapsed.inMinutes < 1) return 'hace un momento';
  if (elapsed.inMinutes < 60) return 'hace ${elapsed.inMinutes} min';
  if (elapsed.inHours < 24) return 'hace ${elapsed.inHours} h';
  return 'hace ${elapsed.inDays} d';
}

String _eventLabel(SeismicEvent event) {
  final String magnitude = event.magnitude == null
      ? 'Sismo'
      : 'M ${event.magnitude!.toStringAsFixed(1)}';
  return event.place == null ? magnitude : '$magnitude · ${event.place}';
}
