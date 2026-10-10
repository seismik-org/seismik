import 'package:flutter/material.dart';
import 'in_app_browser.dart';

abstract final class AppLinks {
  static const terms = 'https://seismik.org/terms-of-service';
  static const privacy = 'https://seismik.org/terms-of-privacy';
  static const source = 'https://github.com/seismik-org/seismik';
  static const deleteAccount = 'https://seismik.org/delete-account/';

  static Future<void> open(BuildContext context, String url) async {
    try {
      if (!await openWebLink(Uri.parse(url))) {
        throw StateError('Link unavailable');
      }
    } catch (_) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('No se pudo abrir el enlace. Inténtalo de nuevo.'),
          ),
        );
      }
    }
  }
}
