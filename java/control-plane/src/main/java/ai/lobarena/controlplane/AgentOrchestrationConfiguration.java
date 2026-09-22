package ai.lobarena.controlplane;

import java.net.URI;
import java.time.Duration;
import java.util.Arrays;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import tools.jackson.databind.ObjectMapper;

@Configuration(proxyBeanMethods = false)
class AgentOrchestrationConfiguration {
    @Bean
    AgentRunnerClient agentRunnerClient(
            ObjectMapper mapper,
            @Value("${lob.agents.runner-timeout-ms:250}") long timeoutMillis) {
        return new HttpAgentRunnerClient(mapper, Duration.ofMillis(timeoutMillis));
    }

    @Bean
    AgentOrchestrator agentOrchestrator(
            AgentRunnerClient client,
            @Value("${lob.agents.runner-urls:http://agent-runner:9100}") String runnerUrls) {
        List<URI> runners = Arrays.stream(runnerUrls.split(","))
                .map(value -> value.trim())
                .filter(value -> !value.isEmpty())
                .map(value -> URI.create(value.endsWith("/") ? value : value + "/"))
                .toList();
        return new AgentOrchestrator(runners, client);
    }
}
