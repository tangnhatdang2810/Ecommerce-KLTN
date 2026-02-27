package hipstershop.model;

import java.util.ArrayList;
import java.util.List;

public class OrderResult {
    private String orderId;
    private String shippingTrackingId;
    private Money shippingCost;
    private Address shippingAddress;
    private List<OrderItem> items = new ArrayList<>();
    private String userId;
    private String email;
    private Money totalCost;
    private String createdAt;
    private String userCurrency;

    public OrderResult() {}

    public String getOrderId() { return orderId; }
    public void setOrderId(String orderId) { this.orderId = orderId; }
    public String getShippingTrackingId() { return shippingTrackingId; }
    public void setShippingTrackingId(String shippingTrackingId) { this.shippingTrackingId = shippingTrackingId; }
    public Money getShippingCost() { return shippingCost; }
    public void setShippingCost(Money shippingCost) { this.shippingCost = shippingCost; }
    public Address getShippingAddress() { return shippingAddress; }
    public void setShippingAddress(Address shippingAddress) { this.shippingAddress = shippingAddress; }
    public List<OrderItem> getItems() { return items; }
    public void setItems(List<OrderItem> items) { this.items = items; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public Money getTotalCost() { return totalCost; }
    public void setTotalCost(Money totalCost) { this.totalCost = totalCost; }
    public String getCreatedAt() { return createdAt; }
    public void setCreatedAt(String createdAt) { this.createdAt = createdAt; }
    public String getUserCurrency() { return userCurrency; }
    public void setUserCurrency(String userCurrency) { this.userCurrency = userCurrency; }
}
