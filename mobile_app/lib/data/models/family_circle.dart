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

class FamilyMember {
  const FamilyMember({
    required this.displayName,
    required this.isYou,
    required this.location,
  });

  factory FamilyMember.fromMap(Map<String, dynamic> map) => FamilyMember(
        displayName: map['display_name']?.toString() ?? 'Familiar',
        isYou: map['is_you'] == true,
        location: map['location'] is Map<String, dynamic>
            ? FamilyLocation.fromMap(map['location'] as Map<String, dynamic>)
            : null,
      );

  final String displayName;
  final bool isYou;
  final FamilyLocation? location;
}

class FamilyCircle {
  const FamilyCircle({
    required this.circleId,
    required this.circleName,
    required this.members,
  });

  factory FamilyCircle.fromMap(Map<String, dynamic> map) => FamilyCircle(
        circleId: map['circle_id']?.toString() ?? '',
        circleName: map['circle_name']?.toString() ?? 'Mi círculo',
        members: (map['members'] as List<dynamic>? ?? <dynamic>[])
            .whereType<Map<String, dynamic>>()
            .map(FamilyMember.fromMap)
            .toList(growable: false),
      );

  final String circleId;
  final String circleName;
  final List<FamilyMember> members;
}
