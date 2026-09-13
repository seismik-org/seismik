/// Persona con sesión iniciada en Seismik.
class SeismikAccount {
  const SeismikAccount({
    required this.uid,
    required this.email,
    required this.name,
  });

  factory SeismikAccount.fromMap(Map<String, dynamic> map) => SeismikAccount(
    uid: map['uid']?.toString() ?? '',
    email: map['email']?.toString() ?? '',
    name: map['name']?.toString() ?? '',
  );

  final String uid;
  final String email;
  final String name;

  /// Primer nombre, para proponerlo como nombre visible en el círculo.
  String get firstName {
    final String trimmed = name.trim();
    if (trimmed.isEmpty) return email.split('@').first;
    return trimmed.split(RegExp(r'\s+')).first;
  }

  Map<String, String> toMap() => <String, String>{
    'uid': uid,
    'email': email,
    'name': name,
  };
}
