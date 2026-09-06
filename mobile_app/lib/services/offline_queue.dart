import 'package:shared_preferences/shared_preferences.dart';

import '../data/models/pending_report.dart';

/// Resultado de un intento de sincronización de la cola offline.
class QueueFlushResult {
  const QueueFlushResult({
    required this.sent,
    required this.remaining,
    required this.discarded,
    this.lastError,
  });

  final int sent;
  final int remaining;
  final int discarded;
  final String? lastError;

  bool get changed => sent > 0 || discarded > 0;
}

/// Excepción que el emisor lanza cuando el servidor rechaza el reporte de forma
/// definitiva (por ejemplo, un cuerpo inválido). Esos reportes no se reintentan.
class PermanentReportRejection implements Exception {
  const PermanentReportRejection(this.message);
  final String message;

  @override
  String toString() => 'PermanentReportRejection: $message';
}

/// Cola persistente de reportes ciudadanos creados sin conexión.
///
/// Un sismo suele dejar a la gente sin datos justo cuando más importa reportar.
/// La cola guarda el reporte tal cual se compuso y lo reenvía cuando la red
/// vuelve; el `report_id` estable hace que un reintento no cree duplicados.
class OfflineReportQueue {
  const OfflineReportQueue({
    this.maxEntries = 50,
    this.maxAttempts = 12,
    this.maxAge = const Duration(days: 30),
  });

  static const String _storageKey = 'seismik.pending_reports';

  final int maxEntries;
  final int maxAttempts;
  final Duration maxAge;

  Future<List<PendingReport>> load() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    final List<String> raw =
        preferences.getStringList(_storageKey) ?? <String>[];
    return raw.map(PendingReport.tryDecode).whereType<PendingReport>().toList();
  }

  Future<int> pendingCount() async => (await load()).length;

  /// Guarda un reporte al final de la cola, sustituyendo el mismo `report_id`.
  Future<void> enqueue(PendingReport report) async {
    final List<PendingReport> queue = await load()
      ..removeWhere((item) => item.reportId == report.reportId);
    queue.add(report);
    // Ante saturación se conservan los reportes más recientes: son los que
    // todavía describen la emergencia en curso.
    final List<PendingReport> trimmed = queue.length > maxEntries
        ? queue.sublist(queue.length - maxEntries)
        : queue;
    await _write(trimmed);
  }

  Future<void> remove(String reportId) async {
    final List<PendingReport> queue = await load()
      ..removeWhere((item) => item.reportId == reportId);
    await _write(queue);
  }

  Future<void> clear() async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    await preferences.remove(_storageKey);
  }

  /// Reenvía la cola en orden. Se detiene ante el primer fallo transitorio para
  /// no gastar batería ni datos repitiendo un error de red por cada reporte.
  Future<QueueFlushResult> flush(
    Future<void> Function(PendingReport report) send, {
    DateTime? now,
  }) async {
    final DateTime moment = (now ?? DateTime.now()).toUtc();
    final List<PendingReport> queue = await load();
    if (queue.isEmpty) {
      return const QueueFlushResult(sent: 0, remaining: 0, discarded: 0);
    }

    final List<PendingReport> remaining = <PendingReport>[];
    int sent = 0;
    int discarded = 0;
    String? lastError;
    bool offline = false;

    for (final PendingReport report in queue) {
      if (offline) {
        remaining.add(report);
        continue;
      }
      if (_isExpired(report, moment)) {
        discarded++;
        continue;
      }
      try {
        await send(report);
        sent++;
      } on PermanentReportRejection catch (error) {
        discarded++;
        lastError = error.message;
      } catch (error) {
        lastError = error.toString();
        final PendingReport retried = report.copyWith(
          attempts: (report.attempts + 1).clamp(0, maxAttempts),
          lastError: lastError,
        );
        // Una red degradada después de un sismo puede durar días. Alcanzar el
        // límite evita reintentos agresivos, pero nunca borra el testimonio:
        // queda persistido para que la persona lo reintente o lo exporte.
        remaining.add(retried);
        offline = true;
      }
    }

    await _write(remaining);
    return QueueFlushResult(
      sent: sent,
      remaining: remaining.length,
      discarded: discarded,
      lastError: lastError,
    );
  }

  bool _isExpired(PendingReport report, DateTime now) =>
      now.difference(report.queuedAt) > maxAge;

  Future<void> _write(List<PendingReport> queue) async {
    final SharedPreferences preferences = await SharedPreferences.getInstance();
    if (queue.isEmpty) {
      await preferences.remove(_storageKey);
      return;
    }
    await preferences.setStringList(
      _storageKey,
      queue.map((report) => report.encode()).toList(growable: false),
    );
  }
}
