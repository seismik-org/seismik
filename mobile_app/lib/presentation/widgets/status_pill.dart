import 'package:flutter/material.dart';

class StatusPill extends StatelessWidget {
  const StatusPill({required this.online, this.label, super.key});

  final bool online;
  final String? label;

  @override
  Widget build(BuildContext context) {
    final ThemeData theme = Theme.of(context);
    final ColorScheme colors = theme.colorScheme;
    final Color foreground = online
        ? colors.onSecondaryContainer
        : colors.onSurfaceVariant;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: ShapeDecoration(
        color: online ? colors.secondaryContainer : colors.surfaceContainerHigh,
        shape: const StadiumBorder(),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            online ? Icons.cloud_done_outlined : Icons.sync_problem_rounded,
            size: 18,
            color: foreground,
          ),
          const SizedBox(width: 8),
          Flexible(
            child: Text(
              label ??
                  (online
                      ? 'Historial sincronizado'
                      : 'Sincronización pendiente'),
              style: theme.textTheme.labelMedium?.copyWith(color: foreground),
            ),
          ),
        ],
      ),
    );
  }
}
