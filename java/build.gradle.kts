import org.gradle.api.tasks.testing.Test

plugins {
    base
    id("com.google.protobuf") version "0.10.0" apply false
    id("org.springframework.boot") version "4.1.1" apply false
}

allprojects {
    group = "ai.lobarena"
    version = "0.1.0-SNAPSHOT"

    repositories {
        mavenCentral()
    }
}

subprojects {
    tasks.withType<Test>().configureEach {
        useJUnitPlatform()
    }
}
