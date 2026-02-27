package hipstershop;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoCollection;
import com.mongodb.client.MongoDatabase;
import com.mongodb.client.model.Indexes;
import hipstershop.model.Money;
import hipstershop.model.Product;
import jakarta.annotation.PostConstruct;
import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.server.ResponseStatusException;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;

@RestController
@RequestMapping("/api/products")
public class ProductCatalogController {

    private static final Logger logger = LoggerFactory.getLogger(ProductCatalogController.class);
    private final MongoCollection<Document> collection;

    public ProductCatalogController(MongoClient mongoClient) {
        MongoDatabase database = mongoClient.getDatabase("productcatalog");
        this.collection = database.getCollection("products");
    }

    @PostConstruct
    public void init() {
        seedIfEmpty();
        ensureIndexes();
    }

    private void ensureIndexes() {
        try {
            collection.createIndex(Indexes.compoundIndex(
                    Indexes.text("name"),
                    Indexes.text("description")
            ));
            logger.info("Text index on name+description ensured");
        } catch (Exception e) {
            logger.debug("Text index already exists or creation skipped: {}", e.getMessage());
        }
    }

    private void seedIfEmpty() {
        if (collection.countDocuments() > 0) {
            logger.info("Product catalog already has {} products in MongoDB", collection.countDocuments());
            return;
        }
        try {
            InputStream is = getClass().getResourceAsStream("/products.json");
            if (is == null) {
                logger.error("products.json not found in classpath for seeding");
                return;
            }
            String json = new String(is.readAllBytes(), StandardCharsets.UTF_8);
            Document root = Document.parse(json);
            List<Document> products = root.getList("products", Document.class);
            if (products != null && !products.isEmpty()) {
                for (Document p : products) {
                    p.put("_id", p.getString("id"));
                }
                collection.insertMany(products);
                logger.info("Seeded {} products into MongoDB", products.size());
            }
        } catch (Exception e) {
            logger.error("Failed to seed product catalog from JSON", e);
        }
    }

    @GetMapping
    public List<Product> listProducts() {
        List<Product> products = new ArrayList<>();
        for (Document doc : collection.find()) {
            products.add(documentToProduct(doc));
        }
        return products;
    }

    @GetMapping("/{id}")
    public Product getProduct(@PathVariable String id) {
        Document doc = collection.find(new Document("_id", id)).first();
        if (doc == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "No product with ID " + id);
        }
        return documentToProduct(doc);
    }

    @GetMapping("/search")
    public List<Product> searchProducts(@RequestParam("q") String query) {
        Document textFilter = new Document("$text", new Document("$search", query));
        List<Product> results = new ArrayList<>();
        for (Document doc : collection.find(textFilter)) {
            results.add(documentToProduct(doc));
        }
        return results;
    }

    private Product documentToProduct(Document doc) {
        Document priceDoc = doc.get("priceUsd", Document.class);

        Money price = new Money(
                priceDoc.getString("currencyCode"),
                priceDoc.getInteger("units", 0),
                priceDoc.getInteger("nanos", 0)
        );

        Product product = new Product();
        product.setId(doc.getString("_id"));
        product.setName(doc.getString("name"));
        product.setDescription(doc.getString("description"));
        product.setPicture(doc.getString("picture"));
        product.setPriceUsd(price);

        List<String> categories = doc.getList("categories", String.class);
        if (categories != null) {
            product.setCategories(categories);
        }

        return product;
    }
}
