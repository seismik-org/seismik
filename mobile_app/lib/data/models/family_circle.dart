String? _text(Object? value) {
  final String? text = value?.toString().trim();
  return text == null || text.isEmpty ? null : text;
}

class FamilyLocation {
  const FamilyLocation({
    required this.latitude,
    required this.longitude,
    required this.precision,
    required this.sharedAt,
    required this.expiresAt,
  });

  factory FamilyLocation.fromMap(Map<String, dynamic> map) => FamilyLocation(
    latitude: (map['latitude'] as num).toDouble(),
    longitude: (map['longitude'] as num).toDouble(),
    precision: map['precision']?.toString() ?? 'approximate',
    sharedAt: DateTime.tryParse(map['shared_at']?.toString() ?? ''),
    expiresAt: DateTime.tryParse(map['expires_at']?.toString() ?? ''),
  );

  final double latitude;
  final double longitude;
  final String precision;
  final DateTime? sharedAt;
  final DateTime? expiresAt;
}

/// Último aviso de un integrante tras un sismo.
class FamilyStatus {
  const FamilyStatus({
    required this.needsHelp,
    this.message,
    this.eventId,
    this.reportedAt,
    this.expiresAt,
  });

  factory FamilyStatus.fromMap(Map<String, dynamic> map) => FamilyStatus(
    needsHelp: map['status']?.toString() == 'need_help',
    message: _text(map['message']),
    eventId: _text(map['event_id']),
    reportedAt: DateTime.tryParse(map['reported_at']?.toString() ?? ''),
    expiresAt: DateTime.tryParse(map['expires_at']?.toString() ?? ''),
  );

  final bool needsHelp;
  final String? message;
  final String? eventId;
  final DateTime? reportedAt;
  final DateTime? expiresAt;
}

class FamilyMember {
  const FamilyMember({
    required this.memberId,
    required this.displayName,
    required this.isYou,
    required this.isOwner,
    required this.location,
    required this.status,
  });

  factory FamilyMember.fromMap(Map<String, dynamic> map) {
    final String name = map['display_name']?.toString() ?? 'Familiar';
    final bool isYou = map['is_you'] == true;
    return FamilyMember(
      memberId: map['member_id']?.toString() ?? '$name-$isYou',
      displayName: name,
      isYou: isYou,
      isOwner: map['is_owner'] == true,
      location: map['location'] is Map<String, dynamic>
          ? FamilyLocation.fromMap(map['location'] as Map<String, dynamic>)
          : null,
      status: map['status'] is Map<String, dynamic>
          ? FamilyStatus.fromMap(map['status'] as Map<String, dynamic>)
          : null,
    );
  }

  final String memberId;
  final String displayName;
  final bool isYou;
  final bool isOwner;
  final FamilyLocation? location;
  final FamilyStatus? status;

  String get initial {
    final String trimmed = displayName.trim();
    return trimmed.isEmpty
        ? '?'
        : String.fromCharCode(trimmed.runes.first).toUpperCase();
  }
}

class FamilyCircle {
  const FamilyCircle({
    required this.circleId,
    required this.circleName,
    required this.isOwner,
    required this.members,
  });

  factory FamilyCircle.fromMap(Map<String, dynamic> map) => FamilyCircle(
    circleId: map['circle_id']?.toString() ?? '',
    circleName: map['circle_name']?.toString() ?? 'Mi círculo',
    isOwner: map['is_owner'] == true,
    members: (map['members'] as List<dynamic>? ?? <dynamic>[])
        .whereType<Map<String, dynamic>>()
        .map(FamilyMember.fromMap)
        .toList(growable: false),
  );

  final String circleId;
  final String circleName;

  /// Sólo quien creó el círculo puede invitar.
  final bool isOwner;
  final List<FamilyMember> members;

  FamilyMember? get you {
    for (final FamilyMember member in members) {
      if (member.isYou) return member;
    }
    return null;
  }
}
