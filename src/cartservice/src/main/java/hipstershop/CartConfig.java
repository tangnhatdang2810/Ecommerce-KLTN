package hipstershop;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CartConfig {

    @Value("${redis.addr:}")
    private String redisAddr;

    @Bean
    public CartStore cartStore() {
        if (redisAddr != null && !redisAddr.isEmpty()) {
            return new RedisCartStore(redisAddr);
        }
        return new InMemoryCartStore();
    }
}
