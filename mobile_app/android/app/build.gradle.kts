plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
}

// El archivo de Firebase se mantiene fuera de Git porque contiene la
// configuración del proyecto. En desarrollo y releases firmados existe y se
// aplica el plugin; en CI se valida el APK sin copiar credenciales al runner.
if (file("google-services.json").isFile) {
    apply(plugin = "com.google.gms.google-services")
}

android {
    namespace = "com.seismik.app"
    // flutter_secure_storage compila sus dependencias nativas contra API 37.
    // Mantener el proyecto en esa API evita que el almacenamiento de las
    // credenciales de sesión de Seismik falle al generar el release.
    compileSdk = 37
    ndkVersion = flutter.ndkVersion

    compileOptions {
        isCoreLibraryDesugaringEnabled = true
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions { jvmTarget = JavaVersion.VERSION_17.toString() }

    defaultConfig {
        applicationId = "com.seismik.app"
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        manifestPlaceholders["SEISMIK_GOOGLE_MAPS_API_KEY"] =
            (project.findProperty("SEISMIK_GOOGLE_MAPS_API_KEY") as String?)
                ?: System.getenv("SEISMIK_GOOGLE_MAPS_API_KEY")
                ?: ""
    }

    signingConfigs {
        create("release") {
            System.getenv("SEISMIK_KEYSTORE")?.let { storeFile = file(it) }
            storePassword = System.getenv("SEISMIK_KEYSTORE_PASSWORD")
            keyAlias = System.getenv("SEISMIK_KEY_ALIAS")
            keyPassword = System.getenv("SEISMIK_KEY_PASSWORD")
        }
    }

    // Verificación de compilación sin el keystore de producción. Se activa sólo
    // con -PseismikUnsignedReleaseCheck=true y produce un APK firmado en debug,
    // no distribuible: sirve para comprobar Dart AOT, Kotlin y R8 en máquinas
    // que no deben tener acceso a las credenciales de firma.
    val releaseSigningCheckOnly =
        (project.findProperty("seismikUnsignedReleaseCheck") as String?) == "true" &&
            System.getenv("SEISMIK_KEYSTORE").isNullOrEmpty()

    buildTypes {
        release {
            signingConfig = if (releaseSigningCheckOnly) {
                logger.warn(
                    "Seismik: APK de release firmado con la clave de depuración " +
                        "para verificar la compilación. No distribuir este artefacto.",
                )
                signingConfigs.getByName("debug")
            } else {
                signingConfigs.getByName("release")
            }
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
        }
    }
}

flutter { source = "../.." }

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.1.5")
}
