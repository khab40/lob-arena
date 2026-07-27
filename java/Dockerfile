FROM eclipse-temurin:25-jdk-noble AS build

WORKDIR /workspace
COPY java/ java/
COPY contracts/proto/ contracts/proto/
RUN --mount=type=cache,target=/root/.gradle \
    cd java && ./gradlew :control-plane:bootJar --no-daemon

FROM eclipse-temurin:25-jre-noble AS runtime

RUN groupadd --system lobarena \
    && useradd --system --gid lobarena --home-dir /app --shell /usr/sbin/nologin lobarena \
    && mkdir -p /app /app/outputs/diagnostics \
    && chown -R lobarena:lobarena /app
WORKDIR /app
COPY --from=build --chown=lobarena:lobarena /workspace/java/control-plane/build/libs/control-plane-*.jar app.jar

USER lobarena
EXPOSE 8080 50051
ENV LOB_KERNEL_GRPC_ENABLED=true \
    LOB_KERNEL_GRPC_PORT=50051 \
    LOB_KERNEL_OTLP_ENABLED=false \
    LOB_KERNEL_OTLP_METRICS_ENABLED=false \
    JAVA_TOOL_OPTIONS="-Xms256m -Xmx2g -XX:MaxDirectMemorySize=256m -XX:+ExitOnOutOfMemoryError -XX:+HeapDumpOnOutOfMemoryError -XX:HeapDumpPath=/app/outputs/diagnostics/java-kernel.hprof"
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
