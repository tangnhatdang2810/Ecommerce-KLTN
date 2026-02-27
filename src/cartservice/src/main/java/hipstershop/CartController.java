package hipstershop;

import hipstershop.model.Cart;
import hipstershop.model.CartItem;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/cart")
public class CartController {

    private static final Logger logger = LoggerFactory.getLogger(CartController.class);
    private final CartStore store;

    public CartController(CartStore store) {
        this.store = store;
    }

    @PostMapping("/{userId}/items")
    public ResponseEntity<Void> addItem(@PathVariable String userId, @RequestBody CartItem item) {
        logger.debug("AddItem userId={} productId={} quantity={}", userId, item.getProductId(), item.getQuantity());
        try {
            store.addItem(userId, item.getProductId(), item.getQuantity());
            return ResponseEntity.ok().build();
        } catch (Exception e) {
            logger.error("AddItem failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    @PutMapping("/{userId}/items/{productId}")
    public ResponseEntity<Void> updateItemQuantity(@PathVariable String userId,
                                                    @PathVariable String productId,
                                                    @RequestBody CartItem item) {
        logger.debug("UpdateItemQuantity userId={} productId={} quantity={}", userId, productId, item.getQuantity());
        try {
            if (item.getQuantity() <= 0) {
                store.removeItem(userId, productId);
            } else {
                store.updateItemQuantity(userId, productId, item.getQuantity());
            }
            return ResponseEntity.ok().build();
        } catch (Exception e) {
            logger.error("UpdateItemQuantity failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    @DeleteMapping("/{userId}/items/{productId}")
    public ResponseEntity<Void> removeItem(@PathVariable String userId, @PathVariable String productId) {
        logger.debug("RemoveItem userId={} productId={}", userId, productId);
        try {
            store.removeItem(userId, productId);
            return ResponseEntity.ok().build();
        } catch (Exception e) {
            logger.error("RemoveItem failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    @GetMapping("/{userId}")
    public ResponseEntity<Cart> getCart(@PathVariable String userId) {
        logger.debug("GetCart userId={}", userId);
        try {
            Cart cart = store.getCart(userId);
            return ResponseEntity.ok(cart);
        } catch (Exception e) {
            logger.error("GetCart failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    @DeleteMapping("/{userId}")
    public ResponseEntity<Void> emptyCart(@PathVariable String userId) {
        logger.debug("EmptyCart userId={}", userId);
        try {
            store.emptyCart(userId);
            return ResponseEntity.ok().build();
        } catch (Exception e) {
            logger.error("EmptyCart failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }
}
