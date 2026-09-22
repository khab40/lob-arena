package ai.lobarena.controlplane;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.net.URI;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.mockito.ArgumentCaptor;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.WebSocketSession;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;

class ArenaWebSocketHandlerTest {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void sendsVersionedInitialEnvelopeAndDispatchesControlCommands(@TempDir Path output) throws Exception {
        LiveArenaService arena = arena(output);
        ArenaWebSocketHandler handler = new ArenaWebSocketHandler(arena, mapper);
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getId()).thenReturn("client-1");
        when(session.isOpen()).thenReturn(true);

        handler.afterConnectionEstablished(session);
        assertThat(handler.clientCount()).isEqualTo(1);

        ArgumentCaptor<TextMessage> messages = ArgumentCaptor.forClass(TextMessage.class);
        verify(session).sendMessage(messages.capture());
        JsonNode envelope = mapper.readTree(messages.getValue().getPayload());
        assertThat(envelope.path("type").stringValue()).isEqualTo("arena_state");
        assertThat(envelope.path("version").intValue()).isEqualTo(1);
        assertThat(envelope.path("payload").path("tick").longValue()).isZero();

        JsonNode started = handler.dispatch(mapper.readTree(
                "{\"type\":\"arena_control\",\"action\":\"start\"}"));
        assertThat(started.path("running").booleanValue()).isTrue();
        JsonNode scenario = handler.dispatch(mapper.readTree(
                "{\"type\":\"launch_scenario\",\"scenario\":\"layering_like\"}"));
        assertThat(scenario.path("scenario_family").stringValue()).isEqualTo("layering_like");

        handler.afterConnectionClosed(session, CloseStatus.NORMAL);
        assertThat(handler.clientCount()).isZero();
    }

    @Test
    void malformedCommandReturnsVersionedErrorWithoutClosingSession(@TempDir Path output) throws Exception {
        ArenaWebSocketHandler handler = new ArenaWebSocketHandler(arena(output), mapper);
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getId()).thenReturn("client-2");
        when(session.isOpen()).thenReturn(true);
        handler.afterConnectionEstablished(session);

        handler.handleTextMessage(session, new TextMessage("{"));

        ArgumentCaptor<TextMessage> messages = ArgumentCaptor.forClass(TextMessage.class);
        verify(session, org.mockito.Mockito.times(2)).sendMessage(messages.capture());
        JsonNode envelope = mapper.readTree(messages.getAllValues().get(1).getPayload());
        assertThat(envelope.path("type").stringValue()).isEqualTo("arena_error");
        assertThat(envelope.path("version").intValue()).isEqualTo(1);
        assertThat(handler.clientCount()).isEqualTo(1);
    }

    private LiveArenaService arena(Path output) {
        AgentRunnerClient client = (URI runner, JsonNode snapshot) -> CompletableFuture.completedFuture(
                mapper.readTree("{\"agent_ids\":[],\"intents\":[]}"));
        AgentOrchestrator orchestrator = new AgentOrchestrator(List.of(URI.create("http://runner:9100/")), client);
        return new LiveArenaService(mapper, orchestrator, new ArenaJournal(output, mapper));
    }
}
