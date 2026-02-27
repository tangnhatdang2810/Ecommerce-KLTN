package hipstershop.model;

public class CreditCardInfo {
    private String creditCardNumber;
    private int creditCardCvv;
    private int creditCardExpirationYear;
    private int creditCardExpirationMonth;

    public CreditCardInfo() {}

    public String getCreditCardNumber() { return creditCardNumber; }
    public void setCreditCardNumber(String creditCardNumber) { this.creditCardNumber = creditCardNumber; }
    public int getCreditCardCvv() { return creditCardCvv; }
    public void setCreditCardCvv(int creditCardCvv) { this.creditCardCvv = creditCardCvv; }
    public int getCreditCardExpirationYear() { return creditCardExpirationYear; }
    public void setCreditCardExpirationYear(int creditCardExpirationYear) { this.creditCardExpirationYear = creditCardExpirationYear; }
    public int getCreditCardExpirationMonth() { return creditCardExpirationMonth; }
    public void setCreditCardExpirationMonth(int creditCardExpirationMonth) { this.creditCardExpirationMonth = creditCardExpirationMonth; }
}
