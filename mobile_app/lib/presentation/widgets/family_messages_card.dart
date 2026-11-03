import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../services/api_client.dart';
import '../../services/family_messages.dart';
import '../../data/models/family_circle.dart';

class FamilyConversationsCard extends StatefulWidget {
  const FamilyConversationsCard({
    super.key,
    required this.api,
    required this.uid,
    required this.circleId,
    required this.senderId,
    required this.members,
    this.nameFor,
    this.active = true,
    this.hasSignal = true,
  });
  final ApiClient api;
  final String uid, circleId, senderId;
  final List<FamilyMember> members;
  final String Function(FamilyMember)? nameFor;
  final bool active, hasSignal;
  @override
  State<FamilyConversationsCard> createState() =>
      _FamilyConversationsCardState();
}

class _FamilyConversationsCardState extends State<FamilyConversationsCard> {
  String? _recipient;
  String? _notice;
  String _name(FamilyMember member) =>
      widget.nameFor?.call(member) ?? member.displayName;

  @override
  void didUpdateWidget(covariant FamilyConversationsCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (_recipient != null &&
        !widget.members.any((m) => m.memberId == _recipient && !m.isYou)) {
      _recipient = null;
      _notice =
          'Este familiar ya no está en el círculo. Sus pendientes no se enviarán al chat familiar.';
    }
  }

  @override
  Widget build(BuildContext context) {
    final peers = widget.members.where((member) => !member.isYou).toList();
    final selected = peers
        .where((member) => member.memberId == _recipient)
        .firstOrNull;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Conversaciones',
                  style: Theme.of(context).textTheme.titleLarge,
                ),
                const SizedBox(height: 12),
                DropdownButtonFormField<String>(
                  key: ValueKey(_recipient ?? 'family'),
                  initialValue: _recipient ?? 'family',
                  isExpanded: true,
                  decoration: const InputDecoration(
                    labelText: 'Elige con quién hablar',
                  ),
                  items: [
                    const DropdownMenuItem(
                      value: 'family',
                      child: Text('Todo el círculo familiar'),
                    ),
                    for (final member in peers)
                      DropdownMenuItem(
                        value: member.memberId,
                        child: Text(
                          'Privado · ${_name(member)}',
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                  onChanged: (value) => setState(() {
                    _recipient = value == 'family' ? null : value;
                    _notice = null;
                  }),
                ),
                if (_notice != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Text(_notice!),
                  ),
              ],
            ),
          ),
        ),
        FamilyMessagesCard(
          key: ValueKey(
            '${widget.uid}:${widget.circleId}:${_recipient ?? 'family'}',
          ),
          api: widget.api,
          uid: widget.uid,
          circleId: widget.circleId,
          senderId: widget.senderId,
          recipientId: _recipient,
          recipientName: selected == null ? null : _name(selected),
          active: widget.active,
          hasSignal: widget.hasSignal,
        ),
      ],
    );
  }
}

class FamilyMessagesCard extends StatefulWidget {
  const FamilyMessagesCard({
    super.key,
    required this.api,
    required this.uid,
    required this.circleId,
    required this.senderId,
    this.recipientId,
    this.recipientName,
    this.active = true,
    this.hasSignal = true,
  });
  final ApiClient api;
  final String uid;
  final String circleId;
  final String senderId;
  final String? recipientId;
  final String? recipientName;
  final bool active;
  final bool hasSignal;

  @override
  State<FamilyMessagesCard> createState() => _FamilyMessagesCardState();
}

class _FamilyMessagesCardState extends State<FamilyMessagesCard> {
  final _draft = TextEditingController();
  late FamilyMessages _messages;
  Timer? _timer;
  late AppLifecycleListener _lifecycle;
  bool _active = true;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _lifecycle = AppLifecycleListener(
      onStateChange: (state) {
        _active = state == AppLifecycleState.resumed;
        if (_active) unawaited(_sync());
      },
    );
    _init();
    _timer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (_active) unawaited(_sync());
    });
  }

  void _init() {
    _messages = FamilyMessages(
      api: widget.api,
      uid: widget.uid,
      circleId: widget.circleId,
      senderId: widget.senderId,
      recipientId: widget.recipientId,
    );
    final service = _messages;
    unawaited(() async {
      try {
        await service.load();
      } on Object {
        if (mounted && service == _messages) {
          setState(
            () => _error =
                'No se pudo leer la copia guardada. Revisa el almacenamiento del teléfono.',
          );
        }
        return;
      }
      if (!mounted || service != _messages) return;
      setState(() {});
      await _sync();
    }());
  }

  @override
  void didUpdateWidget(covariant FamilyMessagesCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.uid != widget.uid ||
        oldWidget.circleId != widget.circleId ||
        oldWidget.recipientId != widget.recipientId ||
        oldWidget.senderId != widget.senderId) {
      _draft.clear();
      _init();
    }
    if (!oldWidget.active && widget.active) unawaited(_sync());
  }

  Future<void> _sync() async {
    if (_busy || !mounted || !widget.active) return;
    final service = _messages;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await service.sync(hasSignal: widget.hasSignal);
    } catch (_) {
      if (mounted) {
        _error = 'No se pudo guardar. Revisa el almacenamiento del teléfono.';
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _send([String? quick]) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await _messages.enqueue(quick ?? _draft.text);
      if (!mounted) return;
      _draft.clear();
    } catch (error) {
      if (mounted) {
        setState(
          () => _error = error is ArgumentError
              ? 'Escribe entre 1 y 280 caracteres.'
              : error is StateError
              ? 'Tienes 50 mensajes pendientes. Revisa o cancela alguno.'
              : 'No se pudo guardar. Revisa el almacenamiento del teléfono.',
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
    if (mounted) await _sync();
  }

  Future<void> _sms() async {
    final number = TextEditingController();
    final destination = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Enviar por SMS'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Abre Mensajes del teléfono. Necesitas señal móvil y pueden aplicarse cargos del operador. Tú confirmas el envío.',
            ),
            TextField(
              controller: number,
              keyboardType: TextInputType.phone,
              decoration: const InputDecoration(
                labelText: 'Número con código de país',
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancelar'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, number.text.trim()),
            child: const Text('Abrir Mensajes'),
          ),
        ],
      ),
    );
    number.dispose();
    if (!mounted) return;
    if (destination == null ||
        !RegExp(r'^\+?[0-9 ()-]{5,25}$').hasMatch(destination)) {
      return;
    }
    final body = _draft.text.trim().isEmpty
        ? 'Soy tu familiar. Escríbeme cuando puedas. — Seismik'
        : _draft.text.trim();
    final opened = await launchUrl(
      Uri(
        scheme: 'sms',
        path: destination.replaceAll(RegExp(r'[ ()-]'), ''),
        queryParameters: {'body': body},
      ),
      mode: LaunchMode.externalApplication,
    );
    if (!opened && mounted) {
      setState(
        () => _error = 'Este dispositivo no pudo abrir la aplicación de SMS.',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              widget.recipientId == null
                  ? 'Chat familiar'
                  : 'Privado · ${widget.recipientName ?? 'Familiar'}',
              style: Theme.of(context).textTheme.titleLarge,
            ),
            const SizedBox(height: 8),
            Text(
              widget.recipientId == null
                  ? 'Este chat se comparte con todo el círculo.'
                  : 'Esta conversación se comparte solo entre los dos participantes.',
            ),
            const Text(
              'Texto ligero por Internet. Si falla la conexión, queda pendiente en este teléfono. No usa SMS automáticamente y no cambia tu estado de seguridad.',
            ),
            const SizedBox(height: 8),
            for (final m in _messages.received)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 7),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      m['is_you'] == true
                          ? 'Tú · recibido por Seismik'
                          : m['display_name'].toString(),
                      style: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    Text(m['text'].toString()),
                  ],
                ),
              ),
            for (final m in _messages.pending)
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(m['text'].toString()),
                subtitle: const Text('Pendiente · aún no recibido por Seismik'),
                trailing: IconButton(
                  tooltip: 'Cancelar envío pendiente',
                  onPressed: _busy
                      ? null
                      : () async {
                          try {
                            await _messages.cancel(m['message_id'].toString());
                            if (mounted) setState(() {});
                          } on Object {
                            if (mounted) {
                              setState(
                                () => _error =
                                    'No se pudo cancelar el pendiente. Revisa el almacenamiento del teléfono.',
                              );
                            }
                          }
                        },
                  icon: const Icon(Icons.close),
                ),
              ),
            if (_messages.received.isEmpty && _messages.pending.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text('Todavía no hay mensajes.'),
              ),
            if (_messages.notice != null)
              Text(
                _messages.notice!,
                style: TextStyle(color: color.onSurfaceVariant),
              ),
            if (_error != null)
              Text(_error!, style: TextStyle(color: color.error)),
            const SizedBox(height: 12),
            Wrap(
              spacing: 6,
              children:
                  [
                        'Voy al punto de encuentro',
                        'No puedo llamar',
                        'Escríbeme cuando puedas',
                      ]
                      .map(
                        (text) => ActionChip(
                          label: Text(text),
                          onPressed: _busy ? null : () => _send(text),
                        ),
                      )
                      .toList(),
            ),
            TextField(
              controller: _draft,
              maxLength: 280,
              maxLines: 3,
              minLines: 1,
              enabled: !_busy,
              decoration: InputDecoration(
                labelText: widget.recipientId == null
                    ? 'Mensaje para tu familia'
                    : 'Mensaje para ${widget.recipientName ?? 'tu familiar'}',
                hintText: 'Por ejemplo: nos vemos en la entrada del parque',
              ),
            ),
            Wrap(
              spacing: 8,
              children: [
                FilledButton.icon(
                  onPressed: _busy ? null : () => _send(),
                  icon: const Icon(Icons.send),
                  label: const Text('Enviar'),
                ),
                TextButton(
                  onPressed: _busy ? null : _sync,
                  child: Text(
                    _busy ? 'Sincronizando…' : 'Actualizar / reintentar',
                  ),
                ),
                OutlinedButton.icon(
                  onPressed: _sms,
                  icon: const Icon(Icons.sms_outlined),
                  label: const Text('Usar SMS'),
                ),
              ],
            ),
            const Text(
              'Se muestran los últimos 50 mensajes. En el servidor vencen en 24 horas. Recibido por Seismik no significa leído. Sin Internet no llegan mensajes nuevos; sin cobertura móvil tampoco se pueden enviar SMS.',
              style: TextStyle(fontSize: 12),
            ),
          ],
        ),
      ),
    );
  }

  @override
  void dispose() {
    _timer?.cancel();
    _lifecycle.dispose();
    _draft.dispose();
    super.dispose();
  }
}
