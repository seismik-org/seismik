import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';
import 'package:provider/provider.dart';

import '../../data/models/family_circle.dart';
import '../../state/seismik_state.dart';

/// Círculo de seguridad voluntario. No rastrea en segundo plano: cada
/// ubicación se comparte por tiempo limitado y la persona puede borrarla.
class FamilySafetyScreen extends StatefulWidget {
  const FamilySafetyScreen({super.key});

  @override
  State<FamilySafetyScreen> createState() => _FamilySafetyScreenState();
}

class _FamilySafetyScreenState extends State<FamilySafetyScreen> {
  FamilyCircle? _circle;
  String? _error;
  bool _loading = true;
  bool _precise = false;
  int _minutes = 60;

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      _circle = await context.read<SeismikState>().api.fetchFamilyCircle();
    } catch (_) {
      _error = 'No fue posible actualizar el círculo. Revisa tu conexión.';
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _createCircle() async {
    final api = context.read<SeismikState>().api;
    final TextEditingController name = TextEditingController();
    final TextEditingController circle = TextEditingController(text: 'Mi círculo');
    final bool? accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Crear círculo familiar'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(controller: name, decoration: const InputDecoration(labelText: 'Cómo te verán')),
            TextField(controller: circle, decoration: const InputDecoration(labelText: 'Nombre del círculo')),
          ],
        ),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Crear')),
        ],
      ),
    );
    if (accepted != true || name.text.trim().isEmpty) return;
    try {
      await api.createFamilyCircle(
            displayName: name.text,
            circleName: circle.text,
          );
      await _reload();
    } catch (_) {
      _show('No se pudo crear el círculo. Registra el dispositivo e inténtalo otra vez.');
    }
  }

  Future<void> _joinCircle() async {
    final api = context.read<SeismikState>().api;
    final TextEditingController code = TextEditingController();
    final TextEditingController name = TextEditingController();
    final bool? accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Unirme a un círculo'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            TextField(controller: code, decoration: const InputDecoration(labelText: 'Código de invitación')),
            TextField(controller: name, decoration: const InputDecoration(labelText: 'Cómo te verán')),
          ],
        ),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Unirme')),
        ],
      ),
    );
    if (accepted != true || code.text.trim().isEmpty || name.text.trim().isEmpty) return;
    try {
      await api.joinFamilyCircle(
            inviteCode: code.text,
            displayName: name.text,
          );
      await _reload();
    } catch (_) {
      _show('El código no es válido, caducó o el dispositivo ya está en un círculo.');
    }
  }

  Future<void> _invite() async {
    final api = context.read<SeismikState>().api;
    final TextEditingController name = TextEditingController();
    final bool? accepted = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Invitar familiar'),
        content: TextField(controller: name, decoration: const InputDecoration(labelText: 'Nombre de la persona')),
        actions: <Widget>[
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          FilledButton(onPressed: () => Navigator.pop(context, true), child: const Text('Crear código')),
        ],
      ),
    );
    if (accepted != true || name.text.trim().isEmpty) return;
    try {
      final String invite = await api.createFamilyInvitation(name.text);
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Código de invitación'),
          content: SelectableText('$invite\n\nVence en 24 horas. Compártelo sólo con la persona invitada.'),
          actions: <Widget>[
            TextButton(
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: invite));
                if (context.mounted) Navigator.pop(context);
              },
              child: const Text('Copiar'),
            ),
            TextButton(onPressed: () => Navigator.pop(context), child: const Text('Cerrar')),
          ],
        ),
      );
    } catch (_) {
      _show('Sólo quien creó el círculo puede generar invitaciones.');
    }
  }

  Future<void> _shareLocation() async {
    final state = context.read<SeismikState>();
    final ({double latitude, double longitude})? coordinates =
        await state.currentCoordinates();
    if (coordinates == null) {
      _show('Activa la ubicación para compartir tu última posición.');
      return;
    }
    try {
      await state.api.shareFamilyLocation(
            latitude: coordinates.latitude,
            longitude: coordinates.longitude,
            shareMinutes: _minutes,
            precise: _precise,
          );
      _show(_precise ? 'Ubicación precisa compartida temporalmente.' : 'Ubicación aproximada compartida temporalmente.');
      await _reload();
    } catch (_) {
      _show('No se pudo compartir la ubicación.');
    }
  }

  Future<void> _stopSharing() async {
    final api = context.read<SeismikState>().api;
    try {
      await api.stopSharingFamilyLocation();
      await _reload();
    } catch (_) {
      _show('No se pudo borrar la ubicación compartida.');
    }
  }

  void _show(String value) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(value)));

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Scaffold(body: Center(child: CircularProgressIndicator()));
    final FamilyCircle? circle = _circle;
    if (circle == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Búsqueda de familiares')),
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              const Icon(Icons.family_restroom_rounded, size: 56),
              const SizedBox(height: 16),
              Text('Círculo de seguridad', style: Theme.of(context).textTheme.headlineSmall),
              const SizedBox(height: 8),
              const Text('Comparte ubicación sólo cuando tú lo decidas. Se borra automáticamente al vencer el tiempo elegido y nunca activa rastreo en segundo plano.'),
              if (_error != null) Padding(padding: const EdgeInsets.only(top: 12), child: Text(_error!)),
              const Spacer(),
              SizedBox(width: double.infinity, child: FilledButton.icon(onPressed: _createCircle, icon: const Icon(Icons.group_add_outlined), label: const Text('Crear mi círculo'))),
              const SizedBox(height: 10),
              SizedBox(width: double.infinity, child: OutlinedButton(onPressed: _joinCircle, child: const Text('Tengo un código de invitación'))),
            ],
          ),
        ),
      );
    }
    final List<FamilyMember> located = circle.members.where((member) => member.location != null).toList(growable: false);
    final LatLng center = located.isEmpty ? const LatLng(4.65, -74.05) : LatLng(located.first.location!.latitude, located.first.location!.longitude);
    return Scaffold(
      appBar: AppBar(title: Text(circle.circleName), actions: <Widget>[IconButton(onPressed: _reload, icon: const Icon(Icons.refresh_rounded))]),
      body: Column(
        children: <Widget>[
          Expanded(
            child: GoogleMap(
              initialCameraPosition: CameraPosition(target: center, zoom: located.isEmpty ? 5.2 : 12),
              markers: located.map((member) => Marker(markerId: MarkerId(member.displayName), position: LatLng(member.location!.latitude, member.location!.longitude), infoWindow: InfoWindow(title: member.displayName, snippet: member.location!.precision == 'precise' ? 'Ubicación precisa temporal' : 'Ubicación aproximada temporal'))).toSet(),
              mapToolbarEnabled: false,
              zoomControlsEnabled: false,
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.all(16),
              children: <Widget>[
                const Text('Las ubicaciones se muestran sólo mientras cada familiar las comparte. No sustituye los canales de emergencia.', style: TextStyle(fontWeight: FontWeight.w600)),
                const SizedBox(height: 8),
                ...circle.members.map((member) => ListTile(
                      leading: CircleAvatar(child: Text(member.displayName.characters.first.toUpperCase())),
                      title: Text(member.isYou ? '${member.displayName} (tú)' : member.displayName),
                      subtitle: Text(member.location == null ? 'No comparte ubicación ahora' : member.location!.precision == 'precise' ? 'Ubicación precisa temporal' : 'Ubicación aproximada temporal'),
                      trailing: member.location == null ? const Icon(Icons.location_off_outlined) : const Icon(Icons.location_on_outlined),
                    )),
                const Divider(),
                SwitchListTile.adaptive(value: _precise, onChanged: (value) => setState(() => _precise = value), title: const Text('Compartir ubicación precisa'), subtitle: const Text('Desactivado por defecto. Al activarlo, el círculo verá tu posición exacta hasta que venza el tiempo.')),
                DropdownButtonFormField<int>(initialValue: _minutes, decoration: const InputDecoration(labelText: 'Compartir durante'), items: const <DropdownMenuItem<int>>[DropdownMenuItem(value: 15, child: Text('15 minutos')), DropdownMenuItem(value: 60, child: Text('1 hora')), DropdownMenuItem(value: 240, child: Text('4 horas'))], onChanged: (value) => setState(() => _minutes = value ?? 60)),
                const SizedBox(height: 12),
                FilledButton.icon(onPressed: _shareLocation, icon: const Icon(Icons.share_location_rounded), label: const Text('Compartir mi ubicación')),
                TextButton.icon(onPressed: _stopSharing, icon: const Icon(Icons.location_off_rounded), label: const Text('Dejar de compartir y borrar ubicación')),
                OutlinedButton.icon(onPressed: _invite, icon: const Icon(Icons.person_add_alt_1_outlined), label: const Text('Invitar familiar')),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
