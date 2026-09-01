plugins {
    `java-library`
    id("com.google.protobuf")
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(25)
    }
}

sourceSets {
    main {
        proto {
            srcDir("../../contracts/proto")
        }
    }
    test {
        resources {
            srcDir("../../contracts/golden")
        }
    }
}

dependencies {
    api("com.google.protobuf:protobuf-java:4.33.2")
    api("io.grpc:grpc-protobuf:1.81.0")
    api("io.grpc:grpc-stub:1.81.0")
    compileOnly("org.apache.tomcat:annotations-api:6.0.53")
    testImplementation(platform("org.junit:junit-bom:6.1.3"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

protobuf {
    protoc {
        artifact = "com.google.protobuf:protoc:4.33.2"
    }
    plugins {
        create("grpc") {
            artifact = "io.grpc:protoc-gen-grpc-java:1.81.0"
        }
    }
    generateProtoTasks {
        all().configureEach {
            plugins {
                create("grpc")
            }
        }
    }
}
