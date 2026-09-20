plugins {
    id("com.android.application")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

// Mismo archivo de Firebase que la app de teléfono (mismo paquete), fuera de
// Git. Sin él el reloj compila, pero no puede registrarse contra la API.
if (file("google-services.json").isFile) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "com.seismik.seismik_wear"
    compileSdk = flutter.compileSdkVersion
    ndkVersion = flutter.ndkVersion

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        // Misma ficha de Play que la app de teléfono: Play entrega a cada
        // dispositivo el APK que le corresponde.
        applicationId = "com.seismik.app"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        // Wear OS 2 en adelante (Android 9 en el reloj).
        minSdk = 28
        targetSdk = flutter.targetSdkVersion
        // Uses the version code from pubspec.yaml. When using split APKs, 1000 * ABI_VERSION
        // is added automatically by Flutter. (https://developer.android.com/studio/build/configure-apk-splits#configure-APK-versions)
        // You can force using the value of versionCode by specifying the `-P force-version-code-ignoring-abi=true`
        // flag during build.
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    // La misma clave de subida que la app de teléfono: Firebase reconoce el
    // paquete y la firma, y con eso App Check deja registrar el reloj.
    signingConfigs {
        create("release") {
            System.getenv("SEISMIK_KEYSTORE")?.let { storeFile = file(it) }
            storePassword = System.getenv("SEISMIK_KEYSTORE_PASSWORD")
            keyAlias = System.getenv("SEISMIK_KEY_ALIAS")
            keyPassword = System.getenv("SEISMIK_KEY_PASSWORD")
        }
    }

    buildTypes {
        release {
            // Sin keystore (CI o una prueba local) se firma con la clave de
            // depuración: el APK compila y se instala, pero la API lo
            // rechazará porque Google no lo reconoce.
            signingConfig = if (System.getenv("SEISMIK_KEYSTORE").isNullOrEmpty()) {
                logger.warn(
                    "Seismik: reloj firmado con la clave de depuración; " +
                        "sirve para verificar la compilación, no para usarlo.",
                )
                signingConfigs.getByName("debug")
            } else {
                signingConfigs.getByName("release")
            }
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget = org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17
    }
}

flutter {
    source = "../.."
}

dependencies {
    // Data Layer: lee la sesión de la cuenta que publica el teléfono.
    implementation("com.google.android.gms:play-services-wearable:19.0.0")
}
