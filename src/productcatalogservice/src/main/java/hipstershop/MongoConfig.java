package hipstershop;

import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MongoConfig {

    @Value("${mongo.addr:mongodb://mongo-productcatalog:27017}")
    private String mongoAddr;

    @Bean
    public MongoClient mongoClient() {
        return MongoClients.create(mongoAddr);
    }
}
