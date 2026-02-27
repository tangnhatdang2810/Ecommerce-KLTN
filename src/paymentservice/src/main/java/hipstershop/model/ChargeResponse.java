package hipstershop.model;

public class ChargeResponse {
    private String transactionId;

    public ChargeResponse() {}

    public ChargeResponse(String transactionId) {
        this.transactionId = transactionId;
    }

    public String getTransactionId() { return transactionId; }
    public void setTransactionId(String transactionId) { this.transactionId = transactionId; }
}
