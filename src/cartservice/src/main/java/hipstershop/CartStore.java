package hipstershop;

import hipstershop.model.Cart;

/**
 * Interface for cart storage backends.
 */
public interface CartStore {
    void addItem(String userId, String productId, int quantity) throws Exception;
    void updateItemQuantity(String userId, String productId, int quantity) throws Exception;
    void removeItem(String userId, String productId) throws Exception;
    Cart getCart(String userId) throws Exception;
    void emptyCart(String userId) throws Exception;
}
