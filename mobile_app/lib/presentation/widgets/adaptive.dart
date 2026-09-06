import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import '../../core/platform.dart';
import 'liquid_glass.dart';

/// Contenedor de pantalla que respeta el lenguaje de cada plataforma.
///
/// iPhone recibe `CupertinoPageScaffold` con su barra translúcida y el gesto de
/// volver arrastrando; Android conserva `Scaffold` con `AppBar`. El contenido es
/// el mismo widget en ambos casos, así que no hay dos interfaces que mantener.
class AdaptiveScreen extends StatelessWidget {
  const AdaptiveScreen({
    required this.title,
    required this.child,
    this.onClose,
    this.trailing,
    this.materialActions,
    super.key,
  });

  final String title;
  final Widget child;

  /// Cierra una pantalla presentada de forma modal (no empujada).
  final VoidCallback? onClose;
  final Widget? trailing;
  final List<Widget>? materialActions;

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      return CupertinoPageScaffold(
        navigationBar: CupertinoNavigationBar(
          middle: Text(title),
          leading: onClose == null
              ? null
              : CupertinoButton(
                  padding: EdgeInsets.zero,
                  onPressed: onClose,
                  child: const Text('Cerrar'),
                ),
          trailing: trailing,
        ),
        child: SafeArea(bottom: false, child: child),
      );
    }
    return Scaffold(
      appBar: AppBar(
        title: Text(title),
        leading: onClose == null
            ? null
            : IconButton(icon: const Icon(Icons.close), onPressed: onClose),
        actions: materialActions,
      ),
      body: child,
    );
  }
}

/// Ruta con la transición nativa de cada plataforma.
Route<T> adaptiveRoute<T>(WidgetBuilder builder, {String? title}) =>
    usesCupertino
    ? CupertinoPageRoute<T>(builder: builder, title: title)
    : MaterialPageRoute<T>(builder: builder);

enum AdaptiveButtonKind { primary, tinted, destructive }

/// Botón de acción con la forma y el color de cada plataforma.
class AdaptiveButton extends StatelessWidget {
  const AdaptiveButton({
    required this.label,
    required this.onPressed,
    this.icon,
    this.kind = AdaptiveButtonKind.primary,
    super.key,
  });

  final String label;
  final VoidCallback? onPressed;
  final IconData? icon;
  final AdaptiveButtonKind kind;

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      final Widget content = icon == null
          ? Text(label)
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(icon, size: 19),
                const SizedBox(width: 8),
                Flexible(child: Text(label, textAlign: TextAlign.center)),
              ],
            );
      return SizedBox(
        width: double.infinity,
        child: switch (kind) {
          AdaptiveButtonKind.primary => CupertinoButton.filled(
            onPressed: onPressed,
            child: content,
          ),
          AdaptiveButtonKind.tinted => CupertinoButton(
            color: CupertinoColors.tertiarySystemFill.resolveFrom(context),
            onPressed: onPressed,
            child: DefaultTextStyle.merge(
              style: TextStyle(
                color: CupertinoColors.label.resolveFrom(context),
              ),
              child: IconTheme.merge(
                data: IconThemeData(
                  color: CupertinoColors.label.resolveFrom(context),
                ),
                child: content,
              ),
            ),
          ),
          AdaptiveButtonKind.destructive => CupertinoButton(
            color: CupertinoColors.systemRed.resolveFrom(context),
            onPressed: onPressed,
            child: content,
          ),
        },
      );
    }
    final Widget materialIcon = Icon(icon ?? Icons.chevron_right);
    return switch (kind) {
      AdaptiveButtonKind.primary => FilledButton.icon(
        onPressed: onPressed,
        icon: materialIcon,
        label: Text(label),
      ),
      AdaptiveButtonKind.tinted => FilledButton.tonalIcon(
        onPressed: onPressed,
        icon: materialIcon,
        label: Text(label),
      ),
      AdaptiveButtonKind.destructive => FilledButton.icon(
        style: FilledButton.styleFrom(backgroundColor: Colors.red.shade700),
        onPressed: onPressed,
        icon: materialIcon,
        label: Text(label),
      ),
    };
  }
}

/// Tarjeta de contenido: vidrio en iPhone, `Card` en Android.
class AdaptiveCard extends StatelessWidget {
  const AdaptiveCard({
    required this.child,
    this.padding = const EdgeInsets.all(16),
    this.color,
    super.key,
  });

  final Widget child;
  final EdgeInsetsGeometry padding;

  /// Tinte de énfasis (aviso, peligro). En iPhone se aplica bajo el vidrio.
  final Color? color;

  @override
  Widget build(BuildContext context) {
    if (usesCupertino) {
      final Widget card = LiquidGlassCard(padding: padding, child: child);
      if (color == null) return card;
      return DecoratedBox(
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(22),
        ),
        child: card,
      );
    }
    return Card(
      color: color,
      child: Padding(padding: padding, child: child),
    );
  }
}

/// Mensaje breve: alerta nativa en iPhone, `SnackBar` en Android.
///
/// iOS no tiene «snackbar»; usar una allí es la señal más rápida de que una app
/// es Material disfrazada.
Future<void> showAdaptiveNotice(
  BuildContext context, {
  required String message,
  String title = 'Seismik',
}) async {
  if (usesCupertino) {
    await showCupertinoDialog<void>(
      context: context,
      builder: (dialogContext) => CupertinoAlertDialog(
        title: Text(title),
        content: Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(message),
        ),
        actions: <Widget>[
          CupertinoDialogAction(
            isDefaultAction: true,
            onPressed: () => Navigator.of(dialogContext).pop(),
            child: const Text('Entendido'),
          ),
        ],
      ),
    );
    return;
  }
  ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
}
