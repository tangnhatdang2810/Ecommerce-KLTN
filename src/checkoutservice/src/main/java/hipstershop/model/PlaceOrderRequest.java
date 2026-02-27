package hipstershop.model;

public class PlaceOrderRequest {
    private String userId;
    private String userCurrency;
    private Address address;
    private String email;
    private CreditCardInfo creditCard;

    public PlaceOrderRequest() {}

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getUserCurrency() { return userCurrency; }
    public void setUserCurrency(String userCurrency) { this.userCurrency = userCurrency; }
    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public CreditCardInfo getCreditCard() { return creditCard; }
    public void setCreditCard(CreditCardInfo creditCard) { this.creditCard = creditCard; }
}
