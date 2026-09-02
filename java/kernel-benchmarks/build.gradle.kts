plugins {
    application
    java
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

sourceSets {
    main {
        resources {
            srcDir("../../contracts/golden")
        }
    }
    test {
        resources {
            srcDir("../../contracts/golden")
        }
    }
}

dependencies {
    implementation(project(":simulation-kernel"))
    implementation(project(":exchange-proto"))
    implementation("org.openjdk.jmh:jmh-core:1.37")
    annotationProcessor("org.openjdk.jmh:jmh-generator-annprocess:1.37")
    testImplementation(platform("org.junit:junit-bom:6.1.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainClass = "org.openjdk.jmh.Main"
}
