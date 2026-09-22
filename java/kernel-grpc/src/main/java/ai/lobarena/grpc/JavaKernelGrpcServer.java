package ai.lobarena.grpc;

import io.grpc.Server;
import io.grpc.ServerBuilder;
import java.io.IOException;
import java.util.concurrent.TimeUnit;

public final class JavaKernelGrpcServer implements AutoCloseable {
    private final Server server;
    private boolean started;

    public JavaKernelGrpcServer(int port) {
        this(port, new JavaKernelGrpcService());
    }

    public JavaKernelGrpcServer(int port, JavaKernelGrpcService service) {
        if (port < 1 || port > 65_535) {
            throw new IllegalArgumentException("port must be between 1 and 65535");
        }
        if (service == null) {
            throw new IllegalArgumentException("service must not be null");
        }
        server = ServerBuilder.forPort(port)
                .addService(service)
                .build();
    }

    public JavaKernelGrpcServer start() throws IOException {
        server.start();
        started = true;
        return this;
    }

    public int port() {
        return server.getPort();
    }

    public void awaitTermination() throws InterruptedException {
        server.awaitTermination();
    }

    @Override
    public void close() throws InterruptedException {
        if (!started) {
            return;
        }
        server.shutdown();
        if (!server.awaitTermination(5, TimeUnit.SECONDS)) {
            server.shutdownNow();
            server.awaitTermination(5, TimeUnit.SECONDS);
        }
    }

    public static void main(String[] args) throws Exception {
        int port = args.length == 0 ? 50_051 : Integer.parseInt(args[0]);
        // Keep ownership visible: the shutdown hook closes this same instance.
        JavaKernelGrpcServer server = new JavaKernelGrpcServer(port);
        server.start();
        Runtime.getRuntime().addShutdownHook(new Thread(() -> {
            try {
                server.close();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
            }
        }));
        System.out.printf("Java kernel gRPC server listening on port %d%n", server.port());
        server.awaitTermination();
    }
}
