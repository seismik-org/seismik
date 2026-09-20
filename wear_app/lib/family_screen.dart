import 'package:flutter/material.dart';

import 'family.dart';
import 'theme.dart';

/// Familia en la muñeca: avisar que estás bien es lo primero que se hace tras
/// un sismo, y es donde un reloj gana al teléfono. Dos botones grandes, porque
/// se tocan con prisa, y debajo lo que avisó cada quien.
class FamilyScreen extends StatefulWidget {
  const FamilyScreen({required this.family, this.eventId, super.key});

  final WearFamily family;

  /// Sismo que motivó el aviso, para que la familia sepa a qué responde.
  final String? eventId;

  @override
  State<FamilyScreen> createState() => _FamilyScreenState();
}

class _FamilyScreenState extends State<FamilyScreen> {
  FamilyCircle? _circle;
  bool _loading = true;
  bool _sending = false;
  String? _message;
  bool _signedIn = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _message = null;
    });
    try {
      final String? session = await widget.family.session();
      if (session == null) {
        if (mounted) {
          setState(() {
            _signedIn = false;
            _loading = false;
          });
        }
        return;
      }
      final FamilyCircle? circle = await widget.family.circle();
      if (!mounted) return;
      setState(() {
        _circle = circle;
        _signedIn = true;
        _loading = false;
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _message = '$error';
        _loading = false;
      });
    }
  }

  Future<void> _report({required bool needsHelp}) async {
    setState(() {
      _sending = true;
      _message = null;
    });
    try {
      await widget.family.report(needsHelp: needsHelp, eventId: widget.eventId);
      if (!mounted) return;
      setState(() {
        _sending = false;
        _message = needsHelp
            ? 'Tu familia ya sabe que necesitas ayuda.'
            : 'Tu familia ya sabe que estás bien.';
      });
      await _load();
    } on Object catch (error) {
      if (!mounted) return;
      setState(() {
        _sending = false;
        _message = '$error';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final FamilyCircle? circle = _circle;
    return Scaffold(
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 10, 18, 28),
          children: <Widget>[
            Text(
              circle?.name ?? 'Mi familia',
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            if (!_signedIn)
              const _Note(
                text:
                    'Inicia sesión en Seismik en tu teléfono para avisar a tu '
                    'familia desde el reloj.',
              )
            else ...<Widget>[
              _ReportButton(
                label: 'Estoy bien',
                color: const Color(0xFF16A34A),
                enabled: !_sending,
                onPressed: () => _report(needsHelp: false),
              ),
              const SizedBox(height: 8),
              _ReportButton(
                label: 'Necesito ayuda',
                color: const Color(0xFFDC2626),
                enabled: !_sending,
                onPressed: () => _report(needsHelp: true),
              ),
              if (_message != null) ...<Widget>[
                const SizedBox(height: 10),
                _Note(text: _message!),
              ],
              const SizedBox(height: 14),
              if (_loading)
                const _Note(text: 'Consultando a tu familia…')
              else
                for (final FamilyMember member in circle?.members ?? const <FamilyMember>[])
                  _MemberRow(member: member),
            ],
          ],
        ),
      ),
    );
  }
}

class _ReportButton extends StatelessWidget {
  const _ReportButton({
    required this.label,
    required this.color,
    required this.enabled,
    required this.onPressed,
  });

  final String label;
  final Color color;
  final bool enabled;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) => SizedBox(
    height: 46,
    child: FilledButton(
      onPressed: enabled ? onPressed : null,
      style: FilledButton.styleFrom(
        backgroundColor: color,
        foregroundColor: Colors.white,
        disabledBackgroundColor: color.withValues(alpha: 0.4),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(23),
        ),
      ),
      child: Text(
        label,
        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w800),
      ),
    ),
  );
}

class _MemberRow extends StatelessWidget {
  const _MemberRow({required this.member});

  final FamilyMember member;

  @override
  Widget build(BuildContext context) {
    final Color color = switch (member.needsHelp) {
      true => const Color(0xFFFF6B6B),
      false => const Color(0xFF4ADE80),
      null => wearMuted,
    };
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: wearSurface,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: <Widget>[
          Container(
            width: 10,
            height: 10,
            margin: const EdgeInsets.only(right: 10),
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  member.isYou ? '${member.name} · Tú' : member.name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(color: Colors.white, fontSize: 12),
                ),
                Text(
                  member.statusLabel,
                  style: TextStyle(color: color, fontSize: 11),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Note extends StatelessWidget {
  const _Note({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) => Text(
    text,
    textAlign: TextAlign.center,
    style: const TextStyle(color: wearMuted, fontSize: 11, height: 1.35),
  );
}
