# Seismik — Sprint 6: integraciones oficiales e IoT

**Estado:** en ejecución — base segura de integraciones terminada el 3 de septiembre de 2026.

## Entregado en esta iteración

| Componente | Resultado verificable |
| --- | --- |
| Reporte oficial | La cadena `OfficialReportUpdate` ya normaliza y conserva fuente, atribución, magnitud, profundidad y URL oficial. |
| Webhooks institucionales | `POST`, `GET` y `DELETE /v1/developer/webhooks`, bajo sesión OAuth del portal; la API key no puede gestionar webhooks. |
| Portal | `devs.seismik.org` permite crear, consultar y desactivar la integración y muestra el secreto de firma una sola vez. |
| Seguridad | Sólo HTTPS público, secreto de firma mostrado una vez, HMAC SHA-256, identificador de entrega, auditoría Redis y aislamiento de errores. |
| Disponibilidad | `stream:seismik:integrations`, consumer independiente y dead-letter después de cinco intentos. Una URL externa lenta no bloquea push móvil. |
| IoT | Contrato de **simulación obligatoria**. No se implementó ni autorizó control de actuadores físicos. |

## Contrato de entrega

```json
{
  "version": "2026-09-03",
  "safety_mode": "simulation_only",
  "action_prohibited": "Do not use this event to control physical equipment or life-safety systems.",
  "event": { "type": "official_report_update" }
}
```

La firma es `HMAC_SHA256(signing_secret, timestamp + "." + raw_body)`. El
receptor debe validar la firma, rechazar timestamps fuera de ventana y hacer
idempotencia con `X-Seismik-Delivery-Id`.

## Pendiente para cerrar el Sprint 6

1. Ejecutar un simulacro con una URL webhook controlada por una universidad/empresa.
2. Revisar con asesor científico la política de qué candidatos preliminares pueden exportarse.
3. Diseñar, sin activar, el perfil de seguridad funcional de cada integración IoT:
   interlock local, modo fallo-seguro, operador responsable y doble confirmación.
4. No conectar ascensores, gas, agua o electricidad hasta contar con certificación,
   acuerdos de operación y pruebas de laboratorio independientes.
