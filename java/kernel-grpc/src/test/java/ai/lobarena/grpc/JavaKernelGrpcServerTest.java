package ai.lobarena.grpc;

import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

final class JavaKernelGrpcServerTest {
    @Test
    void validatesNetworkPortBeforeBuildingServer() {
        assertThrows(IllegalArgumentException.class, () -> new JavaKernelGrpcServer(0));
        assertThrows(IllegalArgumentException.class, () -> new JavaKernelGrpcServer(65_536));
    }

    @Test
    void acceptsValidNetworkPort() {
        try (JavaKernelGrpcServer server = new JavaKernelGrpcServer(50_051)) {
            // Construction validates configuration without binding a shared test port.
            assertThrows(IllegalStateException.class, server::port);
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new AssertionError(exception);
        }
    }
}
