package hipstershop.model;

public class ChargeRequest {
    private Money amount;
    private CreditCardInfo creditCard;

    public ChargeRequest() {}

    public Money getAmount() { return amount; }
    public void setAmount(Money amount) { this.amount = amount; }
    public CreditCardInfo getCreditCard() { return creditCard; }
    public void setCreditCard(CreditCardInfo creditCard) { this.creditCard = creditCard; }
}
