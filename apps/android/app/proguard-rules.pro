# PureGamma release rules.
#
# Gson relies on reflection against DTO/model fields. R8 must not rename or
# strip them or release builds silently deserialize to null/defaults.
-keep class ai.puregamma.android.data.remote.dto.** { *; }
-keep class ai.puregamma.android.model.** { *; }
-keep class * extends com.google.gson.reflect.TypeToken { *; }
-keep class com.google.gson.reflect.TypeToken { *; }
-keepattributes Signature
-keepattributes *Annotation*

# Retrofit interfaces are referenced reflectively by the generated call adapters.
-keep,allowobfuscation,allowshrinking interface ai.puregamma.android.data.remote.PureGammaApi

-dontwarn org.json.**
