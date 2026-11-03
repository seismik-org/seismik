/// Safe Spanish UI messages; raw server details remain available for typed logic.
String translatedApiError(String detail, int? status, {String? code}) {
  const known = <String, String>{
    'Account session required': 'Inicia sesión para usar esta función.',
    'Account session expired': 'Tu sesión venció. Inicia sesión de nuevo.',
    'Account session invalid':
        'Tu sesión ya no es válida. Inicia sesión de nuevo.',
    'Device is not registered':
        'El registro de este teléfono está pendiente. Reinténtalo desde Configuración.',
    'Device integrity verification failed':
        'No se pudo verificar esta instalación. Usa la pista de pruebas de Google Play e inténtalo de nuevo.',
    'App Check did not return a token':
        'No se pudo verificar esta instalación. Comprueba Google Play y vuelve a intentar el registro.',
    'Family membership changed; message was not sent':
        'Tu círculo familiar cambió. El mensaje sigue pendiente y no se enviará a otra familia.',
    'Family membership is no longer active':
        'Ya no tienes acceso a este círculo familiar.',
    'Family message recipient is no longer available':
        'Este familiar ya no está disponible en tu círculo. El mensaje no se ha enviado.',
    'Choose another family member':
        'Elige a otro integrante para abrir una conversación privada.',
    'Account changed; message was not sent':
        'La cuenta cambió. El mensaje sigue guardado en la cuenta que lo creó.',
    'Account changed':
        'La cuenta cambió. Actualiza tu familia antes de continuar.',
    'Message expired or device clock is incorrect':
        'El mensaje tiene más de 24 horas o la hora del teléfono es incorrecta. Revísalo antes de enviarlo de nuevo.',
    'Message identifier already used':
        'Este mensaje ya se usó con otro contenido o destinatario. Revísalo antes de volver a enviarlo.',
    'Family limit: 500 messages in 24 hours; use SMS or a safety check-in':
        'El círculo alcanzó su límite de 500 mensajes en 24 horas. El mensaje sigue pendiente; espera antes de reintentar.',
    'Wait before sending another message':
        'Espera un minuto antes de enviar otro mensaje. El texto sigue guardado.',
    'Retry with the same message identifier':
        'El servicio está ocupado. El mensaje sigue pendiente y se reintentará sin duplicarlo.',
    'Unexpected API response':
        'La respuesta del servicio no se pudo interpretar. Vuelve a intentarlo.',
  };
  if (known.containsKey(detail)) return known[detail]!;
  if (detail.startsWith('Account session')) {
    return 'Tu sesión venció o dejó de ser válida. Inicia sesión de nuevo.';
  }
  if (code == 'invalid_response') return known['Unexpected API response']!;
  return switch (status) {
    401 =>
      'La sesión o el registro necesitan actualizarse. Vuelve a intentar el acceso.',
    403 =>
      'No tienes permiso para realizar esta acción. Revisa tu cuenta y el registro del teléfono.',
    404 => 'El recurso solicitado ya no está disponible. Actualiza los datos.',
    409 =>
      'Los datos cambiaron mientras realizabas la acción. Actualiza y vuelve a intentarlo.',
    413 => 'El contenido es demasiado grande para enviarlo.',
    400 || 422 =>
      'Revisa los datos introducidos y la fecha del teléfono antes de continuar.',
    408 || 504 =>
      'Se agotó el tiempo de espera. Los envíos pendientes siguen guardados.',
    429 =>
      'Se alcanzó un límite temporal de solicitudes. Espera antes de reintentar.',
    int value when value >= 500 =>
      'Seismik no pudo completar la solicitud. Vuelve a intentarlo más tarde.',
    _ =>
      'No se pudo completar la solicitud. Comprueba el estado de conexión e inténtalo de nuevo.',
  };
}
