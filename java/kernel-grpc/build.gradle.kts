plugins {
    application
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
    implementation(project(":simulation-kernel"))
    implementation(project(":exchange-proto"))
    implementation("io.grpc:grpc-services:1.83.1")
    runtimeOnly("io.grpc:grpc-netty-shaded:1.83.1")
    testImplementation(platform("org.junit:junit-bom:6.0.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testImplementation("io.grpc:grpc-inprocess:1.83.1")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

application {
    mainClass = "ai.lobarena.grpc.JavaKernelGrpcServer"
}
