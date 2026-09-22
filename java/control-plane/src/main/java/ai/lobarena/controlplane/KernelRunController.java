package ai.lobarena.controlplane;

import ai.lobarena.exchange.v1.SimulationRequest;
import ai.lobarena.exchange.v1.SimulationResult;
import ai.lobarena.kernel.simulation.JavaSimulationKernel;
import com.google.protobuf.InvalidProtocolBufferException;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/kernel")
final class KernelRunController {
    static final int MAX_REQUEST_BYTES = 8 * 1024 * 1024;
    static final MediaType PROTOBUF = MediaType.parseMediaType("application/x-protobuf");

    private final JavaSimulationKernel kernel;

    KernelRunController(JavaSimulationKernel kernel) {
        this.kernel = kernel;
    }

    @PostMapping(
            path = "/run",
            consumes = {"application/x-protobuf", MediaType.APPLICATION_OCTET_STREAM_VALUE},
            produces = "application/x-protobuf")
    ResponseEntity<byte[]> run(@RequestBody byte[] body) {
        if (body.length > MAX_REQUEST_BYTES) {
            throw new ResponseStatusException(
                    HttpStatus.CONTENT_TOO_LARGE,
                    "Protobuf kernel request exceeds 8 MiB");
        }

        SimulationRequest request;
        try {
            request = SimulationRequest.parseFrom(body);
        } catch (InvalidProtocolBufferException exception) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "invalid SimulationRequest Protobuf",
                    exception);
        }

        SimulationResult result;
        try {
            result = kernel.run(request);
        } catch (IllegalArgumentException exception) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, exception.getMessage(), exception);
        }

        return ResponseEntity.ok()
                .contentType(PROTOBUF)
                .header("X-Kernel-Authority", "java")
                .header("X-Kernel-Decision", "java")
                .header(HttpHeaders.CACHE_CONTROL, "no-store")
                .body(result.toByteArray());
    }
}
