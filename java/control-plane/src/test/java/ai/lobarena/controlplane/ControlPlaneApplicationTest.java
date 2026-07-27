package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import java.io.IOException;
import java.nio.file.Path;
import java.util.Properties;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

@SpringBootTest(properties = "lob.arena.output-dir=build/test-output")
final class ControlPlaneApplicationTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void contextLoadsWithKernelBoundary() {
        assertThat(context).isNotNull();
        assertThat(context.containsBean("kernelStatusController")).isTrue();
        assertThat(context.containsBean("kernelRunController")).isTrue();
        assertThat(context.getBeansOfType(ArenaController.class)).hasSize(1);
        assertThat(context.getBeansOfType(ArenaWebSocketHandler.class)).hasSize(1);
        assertThat(context.getBeansOfType(AgentOrchestrationController.class)).hasSize(1);
        assertThat(context.getBeansOfType(ai.lobarena.kernel.simulation.JavaSimulationKernel.class)).hasSize(1);
        assertThat(context.getBeansOfType(PrometheusMeterRegistry.class)).hasSize(1);
        assertThat(context.getBeansOfType(MicrometerKernelGrpcTelemetry.class)).hasSize(1);
        assertThat(context.getBeansOfType(ArenaEventMetrics.class)).hasSize(1);
        PrometheusMeterRegistry meters = context.getBean(PrometheusMeterRegistry.class);
        assertThat(meters.find("lob.arena.events.retained").gauge()).isNotNull();
        assertThat(meters.find("lob.arena.events.archive.bytes").gauge()).isNotNull();
        assertThat(context.getBeansOfType(ai.lobarena.grpc.JavaKernelGrpcServer.class)).isEmpty();
    }

    @Test
    void arenaOutputDirAcceptsRelativeFilesystemPaths() {
        Path output = ArenaConfiguration.normalizePath("../outputs");

        assertThat(output).isAbsolute();
        assertThat(output.getFileName().toString()).isEqualTo("outputs");
    }

    @Test
    void otlpTraceExportIsOptInWithSpringBootProperty() throws IOException {
        Properties properties = new Properties();
        try (var input = ControlPlaneApplicationTest.class.getResourceAsStream("/application.properties")) {
            properties.load(input);
        }

        assertThat(properties.getProperty("management.tracing.export.otlp.enabled"))
                .isEqualTo("${LOB_KERNEL_OTLP_ENABLED:false}");
        assertThat(properties).doesNotContainKey("management.opentelemetry.tracing.export.otlp.enabled");
    }
}
