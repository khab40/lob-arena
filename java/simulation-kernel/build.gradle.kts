plugins {
    `java-library`
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

sourceSets {
    test {
        resources {
            srcDir("../../contracts/golden")
        }
    }
}

dependencies {
    api(project(":exchange-proto"))
    testImplementation(platform("org.junit:junit-bom:6.1.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
