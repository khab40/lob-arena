package ai.lobarena.controlplane;

import java.io.IOException;
import java.time.Instant;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.ConcurrentWebSocketSessionDecorator;
import org.springframework.web.socket.handler.TextWebSocketHandler;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import tools.jackson.databind.node.ObjectNode;

final class ArenaWebSocketHandler extends TextWebSocketHandler {
    private final LiveArenaService arena;
    private final ObjectMapper mapper;
    private final Map<String, WebSocketSession> sessions = new ConcurrentHashMap<>();

    ArenaWebSocketHandler(LiveArenaService arena, ObjectMapper mapper) {
        this.arena = arena;
        this.mapper = mapper;
    }

    @Override
    public void afterConnectionEstablished(WebSocketSession session) throws Exception {
        WebSocketSession safe = new ConcurrentWebSocketSessionDecorator(session, 2_000, 1_048_576);
        sessions.put(session.getId(), safe);
        sendState(safe, arena.state());
    }

    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws Exception {
        WebSocketSession target = sessions.getOrDefault(session.getId(), session);
        try {
            JsonNode command = mapper.readTree(message.getPayload());
            JsonNode state = dispatch(command);
            broadcastState(state);
        } catch (IllegalArgumentException | JacksonException exception) {
            sendError(target, exception.getMessage());
        }
    }

    @Override
    public void afterConnectionClosed(WebSocketSession session, CloseStatus status) {
        sessions.remove(session.getId());
    }

    @Override
    public void handleTransportError(WebSocketSession session, Throwable exception) throws Exception {
        sessions.remove(session.getId());
        if (session.isOpen()) {
            session.close(CloseStatus.SERVER_ERROR);
        }
    }

    @Scheduled(fixedDelayString = "${lob.arena.websocket.stream-interval-ms:500}")
    void broadcastCurrentState() {
        if (!sessions.isEmpty()) {
            broadcastState(arena.state());
        }
    }

    int clientCount() {
        return sessions.size();
    }

    JsonNode dispatch(JsonNode command) {
        String type = command.path("type").asString("");
        if ("arena_control".equals(type)) {
            return switch (command.path("action").asString("")) {
                case "start" -> arena.start();
                case "pause" -> arena.pause();
                case "reset" -> arena.reset();
                default -> throw new IllegalArgumentException("unknown arena control action");
            };
        }
        if ("launch_scenario".equals(type)) {
            return arena.launchScenario(command.path("scenario").asString());
        }
        if ("load_market_data_source".equals(type)) {
            return arena.loadDataSource(
                    command.path("source_type").asString(),
                    command.path("dataset_id").asString());
        }
        throw new IllegalArgumentException("unknown arena command type");
    }

    private void broadcastState(JsonNode state) {
        for (WebSocketSession session : sessions.values()) {
            try {
                sendState(session, state);
            } catch (IOException exception) {
                sessions.remove(session.getId());
                try {
                    session.close(CloseStatus.SERVER_ERROR);
                } catch (IOException ignored) {
                    // Session is already unusable.
                }
            }
        }
    }

    private void sendState(WebSocketSession session, JsonNode state) throws IOException {
        ObjectNode envelope = mapper.createObjectNode()
                .put("type", "arena_state")
                .put("version", 1)
                .put("timestamp", Instant.now().toString())
                .set("payload", state);
        session.sendMessage(new TextMessage(mapper.writeValueAsString(envelope)));
    }

    private void sendError(WebSocketSession session, String detail) throws IOException {
        ObjectNode error = mapper.createObjectNode()
                .put("type", "arena_error")
                .put("version", 1)
                .put("timestamp", Instant.now().toString())
                .put("detail", detail);
        session.sendMessage(new TextMessage(mapper.writeValueAsString(error)));
    }
}
