package hipstershop.model;

public class OrderItem {
    private CartItem item;
    private Money cost;

    public OrderItem() {}

    public OrderItem(CartItem item, Money cost) {
        this.item = item;
        this.cost = cost;
    }

    public CartItem getItem() { return item; }
    public void setItem(CartItem item) { this.item = item; }
    public Money getCost() { return cost; }
    public void setCost(Money cost) { this.cost = cost; }
}
