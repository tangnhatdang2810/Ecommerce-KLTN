package hipstershop;

import hipstershop.model.ChargeRequest;
import hipstershop.model.ChargeResponse;
import hipstershop.model.CreditCardInfo;
import hipstershop.model.Money;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.time.YearMonth;
import java.util.Map;
import java.util.UUID;

@RestController
@RequestMapping("/api/payment")
public class PaymentController {

    private static final Logger logger = LoggerFactory.getLogger(PaymentController.class);
    private final DataSource dataSource;

    public PaymentController(DataSource dataSource) {
        this.dataSource = dataSource;
    }

    @PostConstruct
    public void initDatabase() {
        String sql = """
            CREATE TABLE IF NOT EXISTS transactions (
                id BIGINT AUTO_INCREMENT PRIMARY KEY,
                transaction_id VARCHAR(36) NOT NULL UNIQUE,
                card_type VARCHAR(20) NOT NULL,
                card_last_four CHAR(4) NOT NULL,
                currency_code VARCHAR(3) NOT NULL,
                amount_units BIGINT NOT NULL,
                amount_nanos INT NOT NULL,
                status ENUM('PENDING','SUCCESS','FAILED') NOT NULL DEFAULT 'SUCCESS',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_transaction_id (transaction_id),
                INDEX idx_created_at (created_at),
                INDEX idx_status (status)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
            """;
        try (Connection conn = dataSource.getConnection();
             Statement stmt = conn.createStatement()) {
            stmt.execute(sql);
            logger.info("Database table 'transactions' initialized");
        } catch (Exception e) {
            logger.error("Failed to initialize database", e);
            throw new RuntimeException("Database initialization failed", e);
        }
    }

    @PostMapping("/charge")
    public ResponseEntity<?> charge(@RequestBody ChargeRequest request) {
        Money amount = request.getAmount();
        CreditCardInfo card = request.getCreditCard();
        String cardNumber = card.getCreditCardNumber().replace("-", "").replace(" ", "");

        logger.info("PaymentService#Charge called: amount={}{}.{}, card_ending={}",
                amount.getCurrencyCode(), amount.getUnits(), amount.getNanos(),
                cardNumber.length() >= 4 ? cardNumber.substring(cardNumber.length() - 4) : cardNumber);

        try {
            // Validate card number
            if (cardNumber.isEmpty() || !cardNumber.matches("\\d+")) {
                return ResponseEntity.badRequest().body(Map.of("error", "Credit card info is invalid"));
            }

            // Determine card type
            String cardType = getCardType(cardNumber);
            if (cardType == null) {
                return ResponseEntity.badRequest().body(Map.of("error", "Credit card info is invalid"));
            }

            // Only VISA and MasterCard accepted
            if (!cardType.equals("visa") && !cardType.equals("mastercard")) {
                return ResponseEntity.badRequest().body(Map.of("error",
                        "Sorry, we cannot process " + cardType + " credit cards. Only VISA or MasterCard is accepted."));
            }

            // Validate expiration
            int expMonth = card.getCreditCardExpirationMonth();
            int expYear = card.getCreditCardExpirationYear();
            YearMonth now = YearMonth.now();
            YearMonth expiry = YearMonth.of(expYear, expMonth);

            if (now.isAfter(expiry)) {
                return ResponseEntity.badRequest().body(Map.of("error",
                        "Your credit card (ending " + cardNumber.substring(cardNumber.length() - 4) +
                                ") expired on " + expMonth + "/" + expYear));
            }

            // Generate transaction ID
            String transactionId = UUID.randomUUID().toString();
            String lastFour = cardNumber.substring(cardNumber.length() - 4);

            // Save transaction to MySQL
            saveTransaction(transactionId, cardType, lastFour,
                    amount.getCurrencyCode(), amount.getUnits(), amount.getNanos());

            logger.info("Transaction processed: {} ending {} Amount: {}{}.{}",
                    cardType, lastFour,
                    amount.getCurrencyCode(), amount.getUnits(), amount.getNanos());

            return ResponseEntity.ok(new ChargeResponse(transactionId));

        } catch (Exception e) {
            logger.error("Payment processing failed", e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(Map.of("error", "Payment processing failed: " + e.getMessage()));
        }
    }

    private void saveTransaction(String transactionId, String cardType, String lastFour,
                                 String currencyCode, long units, int nanos) {
        String sql = "INSERT INTO transactions (transaction_id, card_type, card_last_four, currency_code, amount_units, amount_nanos, status) VALUES (?, ?, ?, ?, ?, ?, ?)";
        try (Connection conn = dataSource.getConnection();
             PreparedStatement ps = conn.prepareStatement(sql)) {
            ps.setString(1, transactionId);
            ps.setString(2, cardType);
            ps.setString(3, lastFour);
            ps.setString(4, currencyCode);
            ps.setLong(5, units);
            ps.setInt(6, nanos);
            ps.setString(7, "SUCCESS");
            ps.executeUpdate();
            logger.info("Transaction {} saved to database with status SUCCESS", transactionId);
        } catch (Exception e) {
            logger.error("Failed to save transaction {} to database", transactionId, e);
        }
    }

    private String getCardType(String number) {
        if (number.startsWith("4")) {
            return "visa";
        } else if (number.length() >= 2) {
            int prefix = Integer.parseInt(number.substring(0, 2));
            if (prefix >= 51 && prefix <= 55) {
                return "mastercard";
            }
            if (number.length() >= 4) {
                int prefix4 = Integer.parseInt(number.substring(0, 4));
                if (prefix4 >= 2221 && prefix4 <= 2720) {
                    return "mastercard";
                }
            }
            if (number.startsWith("34") || number.startsWith("37")) {
                return "amex";
            }
            if (number.startsWith("6011") || number.startsWith("65")) {
                return "discover";
            }
        }
        return "unknown";
    }
}
