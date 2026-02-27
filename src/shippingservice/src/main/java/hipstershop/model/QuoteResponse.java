package hipstershop.model;

public class QuoteResponse {
    private Money costUsd;

    public QuoteResponse() {}

    public QuoteResponse(Money costUsd) {
        this.costUsd = costUsd;
    }

    public Money getCostUsd() { return costUsd; }
    public void setCostUsd(Money costUsd) { this.costUsd = costUsd; }
}
