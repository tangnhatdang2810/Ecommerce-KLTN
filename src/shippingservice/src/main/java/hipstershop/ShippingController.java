package hipstershop;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import hipstershop.model.*;
import jakarta.annotation.PostConstruct;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.web.bind.annotation.*;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;

@RestController
@RequestMapping("/api/shipping")
public class ShippingController {

    private static final Logger logger = LoggerFactory.getLogger(ShippingController.class);
    private final MongoCollection<Document> shipmentsCollection;

    public ShippingController(MongoClient mongoClient) {
        MongoDatabase database = mongoClient.getDatabase("shippingdb");
        this.shipmentsCollection = database.getCollection("shipments");
    }

    @PostConstruct
    public void init() {
        ensureIndexes();
        logger.info("ShippingService connected to MongoDB database 'shippingdb'");
    }

    private void ensureIndexes() {
        try {
            shipmentsCollection.createIndex(Indexes.ascending("trackingId"));
            shipmentsCollection.createIndex(Indexes.ascending("status"));
            logger.info("Indexes on trackingId and status ensured");
        } catch (Exception e) {
            logger.debug("Index creation skipped: {}", e.getMessage());
        }
    }

    @PostMapping("/quote")
    public QuoteResponse getQuote(@RequestBody ShippingRequest request) {
        int itemCount = 0;
        if (request.getItems() != null) {
            for (CartItem item : request.getItems()) {
                itemCount += item.getQuantity();
            }
        }

        Money shippingCost = new Money("USD", 8, 990000000);
        logger.info("Getting shipping quote for {} items, cost: $8.99", itemCount);

        return new QuoteResponse(shippingCost);
    }

    @PostMapping("/order")
    public ShipResponse shipOrder(@RequestBody ShippingRequest request) {
        Address address = request.getAddress();
        String baseStr = (address != null)
                ? address.getStreetAddress() + address.getCity() + address.getState() + address.getZipCode()
                : "";

        String trackingId = createTrackingId(baseStr);

        List<Document> itemDocs = new ArrayList<>();
        if (request.getItems() != null) {
            for (CartItem item : request.getItems()) {
                itemDocs.add(new Document()
                        .append("productId", item.getProductId())
                        .append("quantity", item.getQuantity()));
            }
        }

        Document shipment = new Document()
                .append("trackingId", trackingId)
                .append("address", address != null ? new Document()
                        .append("streetAddress", address.getStreetAddress())
                        .append("city", address.getCity())
                        .append("state", address.getState())
                        .append("country", address.getCountry())
                        .append("zipCode", address.getZipCode()) : new Document())
                .append("items", itemDocs)
                .append("status", "SHIPPED")
                .append("shippedAt", Instant.now().toString());

        try {
            shipmentsCollection.insertOne(shipment);
            logger.info("Shipment saved to MongoDB, tracking ID: {}", trackingId);
        } catch (Exception e) {
            logger.error("Failed to save shipment to MongoDB", e);
        }

        return new ShipResponse(trackingId);
    }

    private String createTrackingId(String salt) {
        Random seeded = new Random(salt.hashCode());
        char letter1 = (char) ('A' + seeded.nextInt(26));
        char letter2 = (char) ('A' + seeded.nextInt(26));
        int part1 = 100 + seeded.nextInt(900);
        int part2 = 1000000 + seeded.nextInt(9000000);
        return String.format("%c%c-%d-%d", letter1, letter2, part1, part2);
    }
}
