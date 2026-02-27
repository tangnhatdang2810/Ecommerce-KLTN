package hipstershop;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import hipstershop.model.Cart;
import hipstershop.model.CartItem;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import redis.clients.jedis.JedisPool;
import redis.clients.jedis.JedisPoolConfig;
import redis.clients.jedis.Jedis;

/**
 * Redis-backed cart store using JSON serialization.
 */
public class RedisCartStore implements CartStore {

    private static final Logger logger = LoggerFactory.getLogger(RedisCartStore.class);
    private static final int CART_TTL_SECONDS = 86400; // 24 hours
    private final JedisPool pool;
    private final ObjectMapper mapper = new ObjectMapper();

    public RedisCartStore(String redisAddr) {
        String host;
        int port = 6379;
        if (redisAddr.contains(":")) {
            String[] parts = redisAddr.split(":");
            host = parts[0];
            port = Integer.parseInt(parts[1]);
        } else {
            host = redisAddr;
        }
        JedisPoolConfig config = new JedisPoolConfig();
        config.setMaxTotal(10);
        pool = new JedisPool(config, host, port);
        logger.info("Redis cart store initialized at {}:{}", host, port);
    }

    @Override
    public void addItem(String userId, String productId, int quantity) throws Exception {
        try (Jedis jedis = pool.getResource()) {
            String data = jedis.get(userId);
            Cart cart;
            if (data != null) {
                cart = mapper.readValue(data, Cart.class);
            } else {
                cart = new Cart(userId);
            }

            boolean found = false;
            for (CartItem item : cart.getItems()) {
                if (item.getProductId().equals(productId)) {
                    item.setQuantity(item.getQuantity() + quantity);
                    found = true;
                    break;
                }
            }
            if (!found) {
                cart.getItems().add(new CartItem(productId, quantity));
            }

            jedis.setex(userId, CART_TTL_SECONDS, mapper.writeValueAsString(cart));
        }
    }

    @Override
    public void updateItemQuantity(String userId, String productId, int quantity) throws Exception {
        try (Jedis jedis = pool.getResource()) {
            String data = jedis.get(userId);
            Cart cart;
            if (data != null) {
                cart = mapper.readValue(data, Cart.class);
            } else {
                return;
            }

            if (quantity <= 0) {
                cart.getItems().removeIf(item -> item.getProductId().equals(productId));
            } else {
                for (CartItem item : cart.getItems()) {
                    if (item.getProductId().equals(productId)) {
                        item.setQuantity(quantity);
                        break;
                    }
                }
            }

            jedis.setex(userId, CART_TTL_SECONDS, mapper.writeValueAsString(cart));
        }
    }

    @Override
    public void removeItem(String userId, String productId) throws Exception {
        try (Jedis jedis = pool.getResource()) {
            String data = jedis.get(userId);
            if (data != null) {
                Cart cart = mapper.readValue(data, Cart.class);
                cart.getItems().removeIf(item -> item.getProductId().equals(productId));
                jedis.setex(userId, CART_TTL_SECONDS, mapper.writeValueAsString(cart));
            }
        }
    }

    @Override
    public Cart getCart(String userId) throws Exception {
        try (Jedis jedis = pool.getResource()) {
            String data = jedis.get(userId);
            if (data != null) {
                return mapper.readValue(data, Cart.class);
            }
            return new Cart(userId);
        }
    }

    @Override
    public void emptyCart(String userId) {
        try (Jedis jedis = pool.getResource()) {
            Cart emptyCart = new Cart(userId);
            jedis.setex(userId, CART_TTL_SECONDS, mapper.writeValueAsString(emptyCart));
        } catch (JsonProcessingException e) {
            logger.error("Failed to serialize empty cart", e);
        }
    }
}
