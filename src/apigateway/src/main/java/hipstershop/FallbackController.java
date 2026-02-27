package hipstershop;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
public class FallbackController {

    @RequestMapping("/fallback")
    public Mono<Map<String, Object>> fallback() {
        return Mono.just(Map.of(
                "status", 503,
                "error", "Service Unavailable",
                "message", "The requested service is temporarily unavailable. Please try again later."
        ));
    }
}
