package hipstershop;

import hipstershop.model.*;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@RequestMapping("/api/checkout")
public class CheckoutController {

    private static final Logger logger = LoggerFactory.getLogger(CheckoutController.class);
    private final CheckoutService checkoutService;

    public CheckoutController(CheckoutService checkoutService) {
        this.checkoutService = checkoutService;
    }

    @PostMapping
    public ResponseEntity<PlaceOrderResponse> placeOrder(@RequestBody PlaceOrderRequest request) {
        logger.info("[PlaceOrder] user_id={} user_currency={}", request.getUserId(), request.getUserCurrency());
        try {
            OrderResult result = checkoutService.placeOrder(request);
            return ResponseEntity.ok(new PlaceOrderResponse(result));
        } catch (Exception e) {
            logger.error("PlaceOrder failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }

    @GetMapping("/orders/{userId}")
    public ResponseEntity<List<OrderResult>> getOrderHistory(@PathVariable String userId) {
        logger.info("[GetOrderHistory] user_id={}", userId);
        try {
            List<OrderResult> orders = checkoutService.getOrderHistory(userId);
            return ResponseEntity.ok(orders);
        } catch (Exception e) {
            logger.error("GetOrderHistory failed", e);
            return ResponseEntity.internalServerError().build();
        }
    }
}
