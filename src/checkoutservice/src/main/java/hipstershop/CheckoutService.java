package hipstershop;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import hipstershop.model.*;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.*;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

import jakarta.annotation.PostConstruct;
import java.time.Instant;
import java.util.*;

@Service
public class CheckoutService {

    private static final Logger logger = LoggerFactory.getLogger(CheckoutService.class);

    private final RestTemplate restTemplate;
    private final MongoClient mongoClient;

    @Value("${cart.service.addr}")
    private String cartServiceAddr;

    @Value("${productcatalog.service.addr}")
    private String productCatalogServiceAddr;

    @Value("${shipping.service.addr}")
    private String shippingServiceAddr;

    @Value("${payment.service.addr}")
    private String paymentServiceAddr;

    private MongoCollection<Document> ordersCollection;

    public CheckoutService(RestTemplate restTemplate, MongoClient mongoClient) {
        this.restTemplate = restTemplate;
        this.mongoClient = mongoClient;
    }

    @PostConstruct
    public void init() {
        MongoDatabase db = mongoClient.getDatabase("checkoutdb");
        ordersCollection = db.getCollection("orders");
        // Create index on userId for fast lookups
        ordersCollection.createIndex(new Document("userId", 1));
        ordersCollection.createIndex(new Document("createdAt", -1));
        logger.info("CheckoutService: MongoDB orders collection initialized");
    }

    public OrderResult placeOrder(PlaceOrderRequest request) {
        String orderId = UUID.randomUUID().toString();

        // 1. Get user cart
        List<CartItem> cartItems = getUserCart(request.getUserId());
        logger.info("Cart has {} items", cartItems.size());

        // 2. Prepare order items (get product details)
        List<OrderItem> orderItems = prepOrderItems(cartItems);

        // 3. Get shipping quote
        Money shippingCost = quoteShipping(request.getAddress(), cartItems);

        // 4. Calculate total
        Money total = new Money(request.getUserCurrency(), 0, 0);
        total = MoneyUtils.sum(total, shippingCost);
        for (OrderItem item : orderItems) {
            Money itemCost = MoneyUtils.multiplySlow(item.getCost(), item.getItem().getQuantity());
            total = MoneyUtils.sum(total, itemCost);
        }

        // 5. Charge card
        String txId = chargeCard(total, request.getCreditCard());
        logger.info("Payment went through (transaction_id: {})", txId);

        // 6. Ship order
        String trackingId = shipOrder(request.getAddress(), cartItems);

        // 7. Empty cart
        emptyUserCart(request.getUserId());

        // 8. Log order confirmation (email service removed)
        logger.info("Order confirmation would be sent to {} (email service removed)", request.getEmail());

        OrderResult orderResult = new OrderResult();
        orderResult.setOrderId(orderId);
        orderResult.setShippingTrackingId(trackingId);
        orderResult.setShippingCost(shippingCost);
        orderResult.setShippingAddress(request.getAddress());
        orderResult.setItems(orderItems);
        orderResult.setUserId(request.getUserId());
        orderResult.setEmail(request.getEmail());
        orderResult.setTotalCost(total);
        orderResult.setCreatedAt(Instant.now().toString());

        // Save order to MongoDB
        saveOrder(orderResult);

        return orderResult;
    }

    public List<OrderResult> getOrderHistory(String userId) {
        List<OrderResult> orders = new ArrayList<>();
        for (Document doc : ordersCollection.find(new Document("userId", userId))
                .sort(new Document("createdAt", -1))) {
            orders.add(documentToOrder(doc));
        }
        return orders;
    }

    private void saveOrder(OrderResult order) {
        try {
            Document doc = new Document()
                    .append("orderId", order.getOrderId())
                    .append("userId", order.getUserId())
                    .append("email", order.getEmail())
                    .append("shippingTrackingId", order.getShippingTrackingId())
                    .append("shippingCost", moneyToDoc(order.getShippingCost()))
                    .append("shippingAddress", addressToDoc(order.getShippingAddress()))
                    .append("totalCost", moneyToDoc(order.getTotalCost()))
                    .append("createdAt", order.getCreatedAt());

            List<Document> itemDocs = new ArrayList<>();
            for (OrderItem item : order.getItems()) {
                Document itemDoc = new Document()
                        .append("productId", item.getItem().getProductId())
                        .append("quantity", item.getItem().getQuantity())
                        .append("cost", moneyToDoc(item.getCost()));
                itemDocs.add(itemDoc);
            }
            doc.append("items", itemDocs);

            ordersCollection.insertOne(doc);
            logger.info("Order {} saved to MongoDB", order.getOrderId());
        } catch (Exception e) {
            logger.error("Failed to save order {} to MongoDB: {}", order.getOrderId(), e.getMessage());
        }
    }

    private Document moneyToDoc(Money m) {
        if (m == null) return new Document();
        return new Document("currencyCode", m.getCurrencyCode())
                .append("units", m.getUnits())
                .append("nanos", m.getNanos());
    }

    private Document addressToDoc(Address a) {
        if (a == null) return new Document();
        return new Document("streetAddress", a.getStreetAddress())
                .append("city", a.getCity())
                .append("state", a.getState())
                .append("country", a.getCountry())
                .append("zipCode", a.getZipCode());
    }

    private OrderResult documentToOrder(Document doc) {
        OrderResult order = new OrderResult();
        order.setOrderId(doc.getString("orderId"));
        order.setUserId(doc.getString("userId"));
        order.setEmail(doc.getString("email"));
        order.setShippingTrackingId(doc.getString("shippingTrackingId"));
        order.setCreatedAt(doc.getString("createdAt"));

        Document costDoc = doc.get("shippingCost", Document.class);
        if (costDoc != null) {
            order.setShippingCost(docToMoney(costDoc));
        }

        Document totalDoc = doc.get("totalCost", Document.class);
        if (totalDoc != null) {
            order.setTotalCost(docToMoney(totalDoc));
        }

        Document addrDoc = doc.get("shippingAddress", Document.class);
        if (addrDoc != null) {
            Address addr = new Address();
            addr.setStreetAddress(addrDoc.getString("streetAddress"));
            addr.setCity(addrDoc.getString("city"));
            addr.setState(addrDoc.getString("state"));
            addr.setCountry(addrDoc.getString("country"));
            addr.setZipCode(addrDoc.getInteger("zipCode", 0));
            order.setShippingAddress(addr);
        }

        List<OrderItem> items = new ArrayList<>();
        List<Document> itemDocs = doc.getList("items", Document.class);
        if (itemDocs != null) {
            for (Document itemDoc : itemDocs) {
                CartItem cartItem = new CartItem();
                cartItem.setProductId(itemDoc.getString("productId"));
                cartItem.setQuantity(itemDoc.getInteger("quantity", 0));
                OrderItem orderItem = new OrderItem(cartItem, docToMoney(itemDoc.get("cost", Document.class)));
                items.add(orderItem);
            }
        }
        order.setItems(items);
        return order;
    }

    private Money docToMoney(Document doc) {
        if (doc == null) return new Money("USD", 0, 0);
        return new Money(
                doc.getString("currencyCode"),
                doc.get("units") != null ? ((Number) doc.get("units")).longValue() : 0,
                doc.get("nanos") != null ? ((Number) doc.get("nanos")).intValue() : 0
        );
    }

    private List<CartItem> getUserCart(String userId) {
        String url = String.format("http://%s/api/cart/%s", cartServiceAddr, userId);
        Cart cart = restTemplate.getForObject(url, Cart.class);
        return cart != null && cart.getItems() != null ? cart.getItems() : new ArrayList<>();
    }

    private List<OrderItem> prepOrderItems(List<CartItem> cartItems) {
        List<OrderItem> orderItems = new ArrayList<>();
        for (CartItem item : cartItems) {
            String url = String.format("http://%s/api/products/%s", productCatalogServiceAddr, item.getProductId());
            Product product = restTemplate.getForObject(url, Product.class);
            if (product != null) {
                Money price = product.getPriceUsd();
                orderItems.add(new OrderItem(item, price));
            }
        }
        return orderItems;
    }

    private Money quoteShipping(Address address, List<CartItem> items) {
        String url = String.format("http://%s/api/shipping/quote", shippingServiceAddr);
        Map<String, Object> body = new HashMap<>();
        body.put("address", address);
        body.put("items", items);

        @SuppressWarnings("unchecked")
        Map<String, Object> resp = restTemplate.postForObject(url, body, Map.class);
        if (resp != null && resp.containsKey("costUsd")) {
            @SuppressWarnings("unchecked")
            Map<String, Object> costMap = (Map<String, Object>) resp.get("costUsd");
            return new Money(
                    (String) costMap.get("currencyCode"),
                    ((Number) costMap.get("units")).longValue(),
                    ((Number) costMap.get("nanos")).intValue()
            );
        }
        return new Money("USD", 0, 0);
    }

    private String chargeCard(Money total, CreditCardInfo card) {
        String url = String.format("http://%s/api/payment/charge", paymentServiceAddr);
        Map<String, Object> body = new HashMap<>();
        body.put("amount", total);
        body.put("creditCard", card);

        @SuppressWarnings("unchecked")
        Map<String, Object> resp = restTemplate.postForObject(url, body, Map.class);
        if (resp != null && resp.containsKey("transactionId")) {
            return (String) resp.get("transactionId");
        }
        throw new RuntimeException("Payment failed — no transaction ID returned");
    }

    private String shipOrder(Address address, List<CartItem> items) {
        String url = String.format("http://%s/api/shipping/order", shippingServiceAddr);
        Map<String, Object> body = new HashMap<>();
        body.put("address", address);
        body.put("items", items);

        @SuppressWarnings("unchecked")
        Map<String, Object> resp = restTemplate.postForObject(url, body, Map.class);
        if (resp != null && resp.containsKey("trackingId")) {
            return (String) resp.get("trackingId");
        }
        throw new RuntimeException("Shipping failed — no tracking ID returned");
    }

    private void emptyUserCart(String userId) {
        try {
            String url = String.format("http://%s/api/cart/%s", cartServiceAddr, userId);
            restTemplate.delete(url);
        } catch (Exception e) {
            logger.warn("Failed to empty cart for user {}: {}", userId, e.getMessage());
        }
    }
}
