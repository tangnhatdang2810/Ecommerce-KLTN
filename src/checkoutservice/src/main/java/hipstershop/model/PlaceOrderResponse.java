package hipstershop.model;

public class PlaceOrderResponse {
    private OrderResult order;

    public PlaceOrderResponse() {}

    public PlaceOrderResponse(OrderResult order) {
        this.order = order;
    }

    public OrderResult getOrder() { return order; }
    public void setOrder(OrderResult order) { this.order = order; }
}
