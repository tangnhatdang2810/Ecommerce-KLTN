package hipstershop;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import reactor.core.publisher.Mono;

@Configuration
public class LoggingFilter {

    private static final Logger logger = LoggerFactory.getLogger(LoggingFilter.class);

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    public GlobalFilter requestLoggingFilter() {
        return (exchange, chain) -> {
            String method = exchange.getRequest().getMethod().name();
            String path = exchange.getRequest().getURI().getPath();
            String remoteAddr = exchange.getRequest().getRemoteAddress() != null
                    ? exchange.getRequest().getRemoteAddress().getAddress().getHostAddress()
                    : "unknown";

            logger.info(">>> {} {} from {}", method, path, remoteAddr);

            long startTime = System.currentTimeMillis();
            return chain.filter(exchange).then(Mono.fromRunnable(() -> {
                long duration = System.currentTimeMillis() - startTime;
                int status = exchange.getResponse().getStatusCode() != null
                        ? exchange.getResponse().getStatusCode().value()
                        : 0;
                logger.info("<<< {} {} - {} ({}ms)", method, path, status, duration);
            }));
        };
    }
}
