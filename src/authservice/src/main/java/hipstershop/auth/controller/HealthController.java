package hipstershop.auth.controller;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class HealthController {

    @GetMapping("/_healthz")
    public ResponseEntity<String> health() {
        return ResponseEntity.ok("ok");
    }
}
