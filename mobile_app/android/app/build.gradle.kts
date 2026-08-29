plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
    id("com.google.gms.google-services")
}

android {
    namespace = "com.seismik.app"
    compileSdk = flutter.compileSdkVersion
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

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
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
