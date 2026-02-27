package hipstershop.model;

import java.util.List;

public class ShippingRequest {
    private Address address;
    private List<CartItem> items;

    public ShippingRequest() {}

    public Address getAddress() { return address; }
    public void setAddress(Address address) { this.address = address; }
    public List<CartItem> getItems() { return items; }
    public void setItems(List<CartItem> items) { this.items = items; }
}
