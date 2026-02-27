package hipstershop;

import hipstershop.model.Cart;
import hipstershop.model.CartItem;

import java.util.ArrayList;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory cart store for development and testing.
 */
public class InMemoryCartStore implements CartStore {

    private final ConcurrentHashMap<String, Cart> carts = new ConcurrentHashMap<>();

    @Override
    public void addItem(String userId, String productId, int quantity) {
        carts.compute(userId, (key, existingCart) -> {
            Cart cart = existingCart != null ? existingCart : new Cart(userId);

            for (CartItem item : cart.getItems()) {
                if (item.getProductId().equals(productId)) {
                    item.setQuantity(item.getQuantity() + quantity);
                    return cart;
                }
            }
            cart.getItems().add(new CartItem(productId, quantity));
            return cart;
        });
    }

    @Override
    public void updateItemQuantity(String userId, String productId, int quantity) {
        carts.computeIfPresent(userId, (key, cart) -> {
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
            return cart;
        });
    }

    @Override
    public void removeItem(String userId, String productId) {
        carts.computeIfPresent(userId, (key, cart) -> {
            cart.getItems().removeIf(item -> item.getProductId().equals(productId));
            return cart;
        });
    }

    @Override
    public Cart getCart(String userId) {
        return carts.getOrDefault(userId, new Cart(userId));
    }

    @Override
    public void emptyCart(String userId) {
        carts.put(userId, new Cart(userId));
    }
}
