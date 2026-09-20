# Seismik para Wear OS

App acompañante para relojes con Wear OS. Muestra el último sismo, la sacudida
estimada donde está la persona y los eventos recientes. **No alerta por su
cuenta**: las alarmas siguen llegando desde el teléfono emparejado, que las
refleja en el reloj.

## Qué comparte con la app de teléfono

- El **modelo de sacudida** (`packages/seismik_shared`): la intensidad que ve la
  persona en el reloj sale de las mismas fórmulas que usa el servidor para
  decidir la alarma. No hay una cuarta copia de la matemática.
- El **paquete** `com.seismik.app` y la **clave de firma**. Así Firebase
  reconoce al reloj como la misma aplicación y App Check deja registrarlo; en
  Play, ambos APK conviven en una sola ficha y cada dispositivo recibe el suyo.
  Los códigos de versión del reloj van en su propia banda (10001 en adelante).

## Compilar

Para probar que compila, sin firma de producción:

```bash
cd wear_app
flutter pub get
flutter analyze
flutter test
flutter build apk --release
```

Ese APK queda firmado con la clave de depuración: **se instala, pero la API lo
rechaza** porque Google no lo reconoce. Para un reloj de verdad hace falta la
firma de subida, con el mismo script de la app de teléfono:

```powershell
.\tools\build-signed-release.ps1 -Project wear `
  -Keystore ..\..\work\secrets\seismik-upload.jks `
  -PasswordFile ..\..\work\secrets\seismik-upload-password.dpapi `
  -Alias seismik-upload -ApiBaseUrl https://api.seismik.org -Artifact apk
```

`android/app/google-services.json` es el mismo archivo de la app de teléfono y
tampoco se versiona: cópialo de `mobile_app/android/app/`.

## Instalar en el reloj

Con el reloj en modo desarrollador y depuración por Wi-Fi o ADB activada:

```bash
adb connect IP_DEL_RELOJ:5555
adb -s IP_DEL_RELOJ:5555 install -r build/app/outputs/flutter-apk/app-release.apk
```

## Lo que falta

- **Familia** («Estoy a salvo») necesita la sesión de la cuenta, que hoy vive
  sólo en el teléfono. Llevarla al reloj exige sincronizarla por el Data Layer
  de Wear, con código nativo en ambos lados.
- **Tile y complicación** para la esfera: se escriben en Kotlin con Jetpack
  Tiles; Flutter no las dibuja.
- **Alertas propias** en el reloj: hoy llegan reflejadas del teléfono.
