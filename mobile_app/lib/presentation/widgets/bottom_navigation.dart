import 'package:flutter/material.dart';

class SeismikBottomNavigation extends StatelessWidget {
  const SeismikBottomNavigation({
    required this.selectedIndex,
    required this.onSelected,
    super.key,
  });

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
          destinations:
              const <NavigationDestination>[
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
                      icon: Icon(Icons.family_restroom_outlined),
                      selectedIcon: Icon(Icons.family_restroom_rounded),
                      label: 'Familia',
                      tooltip: 'Búsqueda de familiares',
                    ),
                    NavigationDestination(
                      icon: Icon(Icons.tune_rounded),
                      selectedIcon: Icon(Icons.tune_rounded),
                      label: 'Ajustes',
                      tooltip: 'Configuración',
                    ),
                  ]
                  .map(
                    (destination) => DefaultTextStyle.merge(
                      maxLines: 1,
                      softWrap: false,
                      overflow: TextOverflow.ellipsis,
                      child: destination,
                    ),
                  )
                  .toList(growable: false),
        ),
      ),
    );
  }
}
