package ai.lobarena.controlplane;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.regex.Pattern;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

record DuckDbResourceLimits(
        String memoryLimit,
        int threads,
        Path tempDirectory,
        String maxTempDirectorySize) {
    private static final Logger LOGGER = LoggerFactory.getLogger(DuckDbResourceLimits.class);
    private static final Pattern BYTE_SIZE =
            Pattern.compile("[1-9][0-9]*(?:KB|MB|GB|TB|KiB|MiB|GiB|TiB)", Pattern.CASE_INSENSITIVE);

    DuckDbResourceLimits {
        if (memoryLimit == null || !BYTE_SIZE.matcher(memoryLimit).matches()) {
            throw new IllegalArgumentException("DuckDB memory limit must be a positive byte size");
        }
        if (threads < 1 || threads > 64) {
            throw new IllegalArgumentException("DuckDB threads must be between 1 and 64");
        }
        if (tempDirectory == null) {
            throw new IllegalArgumentException("DuckDB temp directory is required");
        }
        tempDirectory = tempDirectory.toAbsolutePath().normalize();
        if (maxTempDirectorySize == null || !BYTE_SIZE.matcher(maxTempDirectorySize).matches()) {
            throw new IllegalArgumentException(
                    "DuckDB maximum temp directory size must be a positive byte size");
        }
    }

    static DuckDbResourceLimits defaults() {
        return new DuckDbResourceLimits(
                "1GB",
                2,
                Path.of(System.getProperty("java.io.tmpdir"), "lob-arena-duckdb"),
                "8GB");
    }

    void apply(Connection connection) throws SQLException, IOException {
        Files.createDirectories(tempDirectory);
        try (Statement settings = connection.createStatement()) {
            settings.execute("SET memory_limit = '" + memoryLimit + "'");
            settings.execute("SET threads = " + threads);
            settings.execute("SET preserve_insertion_order = true");
            settings.execute("SET temp_directory = '" + sqlText(tempDirectory.toString()) + "'");
            settings.execute("SET max_temp_directory_size = '" + maxTempDirectorySize + "'");
        }
        LOGGER.info(
                "Configured DuckDB memory_limit={}, threads={}, preserve_insertion_order=true, "
                        + "temp_directory={}, max_temp_directory_size={}",
                memoryLimit,
                threads,
                tempDirectory,
                maxTempDirectorySize);
    }

    private static String sqlText(String value) {
        return value.replace("'", "''");
    }
}
