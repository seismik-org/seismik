import 'dart:convert';

/// Tipo de reporte ciudadano en espera de sincronización.
enum PendingReportKind {
  felt('felt', '/v1/reports/felt', 'Sismo sentido'),
  damage('damage', '/v1/reports/damage', 'Reporte de daños');

  const PendingReportKind(this.id, this.path, this.label);

  final String id;
  final String path;
  final String label;

  static PendingReportKind fromId(String value) => switch (value) {
    'damage' => PendingReportKind.damage,
    _ => PendingReportKind.felt,
  };
}

/// Reporte guardado en el dispositivo mientras no hay red.
///
/// El cuerpo se conserva tal cual se compuso: `report_id` y `observed_at` no
/// cambian al reintentar, de modo que el servidor pueda descartar duplicados y
/// la hora registrada siga siendo la del sismo, no la de la sincronización.
class PendingReport {
  const PendingReport({
    required this.reportId,
    required this.kind,
    required this.payload,
    required this.queuedAt,
    this.attempts = 0,
    this.lastError,
  });

  factory PendingReport.fromMap(Map<String, dynamic> map) => PendingReport(
    reportId: (map['report_id'] ?? '').toString(),
    kind: PendingReportKind.fromId((map['kind'] ?? 'felt').toString()),
    payload: Map<String, dynamic>.from(
      map['payload'] as Map<dynamic, dynamic>? ?? <dynamic, dynamic>{},
    ),
    queuedAt:
        DateTime.tryParse((map['queued_at'] ?? '').toString())?.toUtc() ??
        DateTime.now().toUtc(),
    attempts: (map['attempts'] as num?)?.toInt() ?? 0,
    lastError: map['last_error']?.toString(),
  );

  static PendingReport? tryDecode(String raw) {
    try {
      final Object? decoded = jsonDecode(raw);
      if (decoded is! Map<String, dynamic>) return null;
      final PendingReport report = PendingReport.fromMap(decoded);
      return report.reportId.isEmpty ? null : report;
    } on FormatException {
      return null;
    }
  }

  final String reportId;
  final PendingReportKind kind;
  final Map<String, dynamic> payload;
  final DateTime queuedAt;
  final int attempts;
  final String? lastError;

  PendingReport copyWith({int? attempts, String? lastError}) => PendingReport(
    reportId: reportId,
    kind: kind,
    payload: payload,
    queuedAt: queuedAt,
    attempts: attempts ?? this.attempts,
    lastError: lastError ?? this.lastError,
  );

  Map<String, dynamic> toMap() => <String, dynamic>{
    'report_id': reportId,
    'kind': kind.id,
    'payload': payload,
    'queued_at': queuedAt.toIso8601String(),
    'attempts': attempts,
    'last_error': lastError,
  };

  String encode() => jsonEncode(toMap());
}
