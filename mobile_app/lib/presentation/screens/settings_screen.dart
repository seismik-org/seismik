import 'package:flutter/material.dart';
import 'package:geolocator/geolocator.dart';

class SettingsScreen extends StatelessWidget {
  const SettingsScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final ColorScheme colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: AppBar(title: const Text('Configuración')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 116),
        children: <Widget>[
          Card(
            child: Padding(
              padding: const EdgeInsets.all(18),
              child: Row(
                children: <Widget>[
                  Image.asset(
                    'assets/images/seismik_logo.png',
                    width: 58,
                    height: 58,
                  ),
                  const SizedBox(width: 14),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: <Widget>[
                        Text(
                          'Seismik',
                          style: TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w900,
                          ),
                        ),
                        Text('Beta experimental 0.5.0'),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
          const SizedBox(height: 10),
          Card(
            child: Column(
              children: <Widget>[
                ListTile(
                  leading: Icon(Icons.palette_outlined, color: colors.primary),
                  title: const Text('Tema Seismik para One UI'),
                  subtitle: const Text(
                    'Paleta índigo exacta · modo claro/oscuro del sistema',
                  ),
                ),
                const Divider(height: 1),
                ListTile(
                  leading: Icon(Icons.map_outlined, color: colors.primary),
                  title: const Text('Proveedor de mapas'),
                  subtitle: const Text('Google Maps Platform'),
                ),
              ],
            ),
          ),
          const SizedBox(height: 10),
          Card(
            child: Column(
              children: <Widget>[
                ListTile(
                  leading: const Icon(Icons.admin_panel_settings_outlined),
                  title: const Text('Permisos del sistema'),
                  subtitle: const Text(
                    'Ubicación, sensores y notificaciones críticas',
                  ),
                  trailing: const Icon(Icons.open_in_new_rounded),
                  onTap: Geolocator.openAppSettings,
                ),
                const Divider(height: 1),
                const ListTile(
                  leading: Icon(Icons.security_outlined),
                  title: Text('Privacidad'),
                  subtitle: Text(
                    'Ubicación aproximada por defecto; reportes oficiales solo con tu decisión.',
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),
          Text(
            'Seismik es un sistema experimental y no reemplaza las instrucciones de las autoridades ni los servicios de emergencia.',
            style: TextStyle(color: colors.onSurfaceVariant),
          ),
        ],
      ),
    );
  }
}
