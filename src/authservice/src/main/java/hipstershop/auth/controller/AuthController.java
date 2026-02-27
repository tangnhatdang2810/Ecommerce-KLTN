package hipstershop.auth.controller;

import hipstershop.auth.model.User;
import hipstershop.auth.repository.UserRepository;
import hipstershop.auth.service.JwtService;
import org.mindrot.jbcrypt.BCrypt;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.time.format.DateTimeFormatter;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Optional;
import java.util.UUID;

@RestController
@RequestMapping("/api")
public class AuthController {

    private static final Logger logger = LoggerFactory.getLogger(AuthController.class);
    private final UserRepository userRepository;
    private final JwtService jwtService;

    public AuthController(UserRepository userRepository, JwtService jwtService) {
        this.userRepository = userRepository;
        this.jwtService = jwtService;
    }

    @PostMapping("/register")
    public ResponseEntity<Map<String, String>> register(@RequestBody Map<String, String> body) {
        String email = trim(body.get("email"));
        String username = trim(body.get("username"));
        String password = body.get("password");
        String firstName = trim(body.getOrDefault("first_name", ""));
        String lastName = trim(body.getOrDefault("last_name", ""));

        // Validation
        if (email.isEmpty() || username.isEmpty() || password == null || password.isEmpty()) {
            return error(HttpStatus.BAD_REQUEST, "email, username, and password are required");
        }
        if (password.length() < 6) {
            return error(HttpStatus.BAD_REQUEST, "password must be at least 6 characters");
        }
        if (!email.contains("@")) {
            return error(HttpStatus.BAD_REQUEST, "invalid email format");
        }

        // Check duplicates
        if (userRepository.existsByEmail(email)) {
            return error(HttpStatus.CONFLICT, "email or username already exists");
        }
        if (userRepository.existsByUsername(username)) {
            return error(HttpStatus.CONFLICT, "email or username already exists");
        }

        // Create user
        User user = new User();
        user.setId(UUID.randomUUID().toString());
        user.setEmail(email);
        user.setUsername(username);
        user.setPasswordHash(BCrypt.hashpw(password, BCrypt.gensalt()));
        user.setFirstName(firstName);
        user.setLastName(lastName);

        userRepository.save(user);

        logger.info("user registered user_id={} email={}", user.getId(), email);

        Map<String, String> resp = new LinkedHashMap<>();
        resp.put("user_id", user.getId());
        resp.put("message", "registration successful");
        return ResponseEntity.status(HttpStatus.CREATED).body(resp);
    }

    @PostMapping("/login")
    public ResponseEntity<?> login(@RequestBody Map<String, String> body) {
        String email = trim(body.get("email"));
        String password = body.get("password");

        if (email.isEmpty() || password == null || password.isEmpty()) {
            return error(HttpStatus.BAD_REQUEST, "email and password are required");
        }

        Optional<User> optUser = userRepository.findByEmail(email);
        if (optUser.isEmpty()) {
            return error(HttpStatus.UNAUTHORIZED, "invalid email or password");
        }

        User user = optUser.get();
        if (!BCrypt.checkpw(password, user.getPasswordHash())) {
            return error(HttpStatus.UNAUTHORIZED, "invalid email or password");
        }

        String token = jwtService.generateToken(user.getId(), user.getEmail());
        long expiresAt = jwtService.getExpirationTimestamp() / 1000;

        logger.info("user logged in user_id={}", user.getId());

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("token", token);
        resp.put("expires_at", expiresAt);
        resp.put("username", user.getUsername());
        return ResponseEntity.ok(resp);
    }

    @GetMapping("/profile")
    public ResponseEntity<?> profile(@RequestHeader(value = "Authorization", required = false) String authHeader) {
        if (authHeader == null || !authHeader.startsWith("Bearer ")) {
            return error(HttpStatus.UNAUTHORIZED, "missing or invalid authorization header");
        }

        String token = authHeader.substring(7);
        String userId = jwtService.getUserIdFromToken(token);
        if (userId == null) {
            return error(HttpStatus.UNAUTHORIZED, "invalid or expired token");
        }

        Optional<User> optUser = userRepository.findById(userId);
        if (optUser.isEmpty()) {
            return error(HttpStatus.NOT_FOUND, "user not found");
        }

        User user = optUser.get();
        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("user_id", user.getId());
        resp.put("email", user.getEmail());
        resp.put("username", user.getUsername());
        resp.put("first_name", user.getFirstName());
        resp.put("last_name", user.getLastName());
        resp.put("created_at", user.getCreatedAt() != null
                ? user.getCreatedAt().format(DateTimeFormatter.ISO_DATE_TIME) : "");
        return ResponseEntity.ok(resp);
    }

    @GetMapping("/_healthz")
    public ResponseEntity<String> health() {
        try {
            userRepository.count();
            return ResponseEntity.ok("ok");
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).body("unhealthy");
        }
    }

    private String trim(String s) {
        return s == null ? "" : s.trim();
    }

    private ResponseEntity<Map<String, String>> error(HttpStatus status, String message) {
        Map<String, String> resp = new LinkedHashMap<>();
        resp.put("error", message);
        return ResponseEntity.status(status).body(resp);
    }
}
