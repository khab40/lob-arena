package ai.lobarena.controlplane;

import ai.lobarena.grpc.JavaKernelGrpcServer;
import ai.lobarena.grpc.JavaKernelGrpcService;
import ai.lobarena.kernel.simulation.JavaSimulationKernel;
import java.io.IOException;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class KernelGrpcConfiguration {
    @Bean
    JavaSimulationKernel javaSimulationKernel() {
        return new JavaSimulationKernel();
    }

    @Bean(destroyMethod = "close")
    @ConditionalOnProperty(name = "lob.kernel.grpc.enabled", havingValue = "true")
    JavaKernelGrpcServer kernelGrpcServer(
            JavaSimulationKernel kernel,
            MicrometerKernelGrpcTelemetry telemetry,
            @Value("${lob.kernel.grpc.port:50051}") int port) throws IOException {
        // Spring owns this instance through destroyMethod; start() returns the same instance.
        JavaKernelGrpcServer server = new JavaKernelGrpcServer(port, new JavaKernelGrpcService(kernel, telemetry));
        server.start();
        return server;
    }
}
