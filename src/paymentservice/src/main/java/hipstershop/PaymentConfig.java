package hipstershop;

import com.zaxxer.hikari.HikariConfig;
import com.zaxxer.hikari.HikariDataSource;
import jakarta.annotation.PostConstruct;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import javax.sql.DataSource;
import java.sql.Connection;
import java.sql.Statement;

@Configuration
public class PaymentConfig {

    private static final Logger logger = LoggerFactory.getLogger(PaymentConfig.class);

    @Value("${mysql.host:mysql-payment}")
    private String mysqlHost;

    @Value("${mysql.port:3306}")
    private String mysqlPort;

    @Value("${mysql.user:paymentuser}")
    private String mysqlUser;

    @Value("${mysql.password:paymentpassword}")
    private String mysqlPassword;

    @Value("${mysql.database:paymentdb}")
    private String mysqlDatabase;

    @Bean
    public DataSource dataSource() {
        String jdbcUrl = String.format("jdbc:mysql://%s:%s/%s?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC",
                mysqlHost, mysqlPort, mysqlDatabase);

        HikariConfig config = new HikariConfig();
        config.setJdbcUrl(jdbcUrl);
        config.setUsername(mysqlUser);
        config.setPassword(mysqlPassword);
        config.setMaximumPoolSize(10);
        config.setMinimumIdle(2);
        config.setConnectionTimeout(30000);

        logger.info("Connecting to MySQL at {}:{}/{}", mysqlHost, mysqlPort, mysqlDatabase);
        return new HikariDataSource(config);
    }

    @PostConstruct
    public void initDatabase() {
        // Deferred to after DataSource bean creation via PaymentController
    }
}
