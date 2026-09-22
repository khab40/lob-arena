package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import ai.lobarena.exchange.v1.SimulationRequest;
import ai.lobarena.exchange.v1.SimulationResult;
import ai.lobarena.kernel.simulation.JavaSimulationKernel;
import java.io.IOException;
import java.io.InputStream;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.server.ResponseStatusException;

final class KernelRunControllerTest {
    private final KernelRunController controller = new KernelRunController(new JavaSimulationKernel());

    @Test
    void returnsExactGoldenResultFromJavaAuthority() throws IOException {
        SimulationRequest request = request("normal-market-seed-42");
        SimulationResult expected = result("normal-market-seed-42");

        ResponseEntity<byte[]> response = controller.run(request.toByteArray());

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getHeaders().getContentType()).isEqualTo(KernelRunController.PROTOBUF);
        assertThat(response.getHeaders().getFirst("X-Kernel-Authority")).isEqualTo("java");
        assertThat(response.getHeaders().getFirst("X-Kernel-Decision")).isEqualTo("java");
        assertThat(SimulationResult.parseFrom(response.getBody())).isEqualTo(expected);
    }

    @Test
    void rejectsMalformedOversizedAndInvalidContractRequests() throws IOException {
        byte[] oversized = new byte[KernelRunController.MAX_REQUEST_BYTES + 1];
        SimulationRequest invalid = request("normal-market-seed-42").toBuilder()
                .setContractVersion(2)
                .build();

        assertStatus(HttpStatus.BAD_REQUEST, () -> controller.run(new byte[] {(byte) 0x80}));
        assertStatus(HttpStatus.CONTENT_TOO_LARGE, () -> controller.run(oversized));
        assertStatus(HttpStatus.BAD_REQUEST, () -> controller.run(invalid.toByteArray()));
    }

    private void assertStatus(HttpStatus expected, Runnable invocation) {
        assertThatThrownBy(invocation::run)
                .isInstanceOf(ResponseStatusException.class)
                .extracting(exception -> ((ResponseStatusException) exception).getStatusCode())
                .isEqualTo(expected);
    }

    private SimulationRequest request(String caseId) throws IOException {
        try (InputStream input = getClass().getResourceAsStream(
                "/parity-v1/cases/" + caseId + "/request.pb")) {
            return SimulationRequest.parseFrom(input);
        }
    }

    private SimulationResult result(String caseId) throws IOException {
        try (InputStream input = getClass().getResourceAsStream(
                "/parity-v1/cases/" + caseId + "/expected-result.pb")) {
            return SimulationResult.parseFrom(input);
        }
    }
}
