package ai.lobarena.controlplane;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

final class ArenaJournal {
    private final Path root;
    private final ObjectMapper mapper;

    ArenaJournal(Path root, ObjectMapper mapper) {
        this.root = root;
        this.mapper = mapper;
    }

    Path root() {
        return root;
    }

    synchronized void append(String relativePath, JsonNode value) {
        Path target = root.resolve(relativePath).normalize();
        if (!target.startsWith(root.normalize())) {
            throw new IllegalArgumentException("journal path escapes output root");
        }
        try {
            Files.createDirectories(target.getParent());
            Files.writeString(
                    target,
                    mapper.writeValueAsString(value) + System.lineSeparator(),
                    StandardCharsets.UTF_8,
                    StandardOpenOption.CREATE,
                    StandardOpenOption.APPEND);
        } catch (IOException exception) {
            throw new IllegalStateException("failed to append arena journal " + relativePath, exception);
        }
    }
}
