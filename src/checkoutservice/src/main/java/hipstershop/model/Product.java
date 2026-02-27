package hipstershop.model;

import java.util.ArrayList;
import java.util.List;

public class Product {
    private String id;
    private String name;
    private String description;
    private String picture;
    private Money priceUsd;
    private List<String> categories = new ArrayList<>();

    public Product() {}

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getName() { return name; }
    public void setName(String name) { this.name = name; }
    public String getDescription() { return description; }
    public void setDescription(String description) { this.description = description; }
    public String getPicture() { return picture; }
    public void setPicture(String picture) { this.picture = picture; }
    public Money getPriceUsd() { return priceUsd; }
    public void setPriceUsd(Money priceUsd) { this.priceUsd = priceUsd; }
    public List<String> getCategories() { return categories; }
    public void setCategories(List<String> categories) { this.categories = categories; }
}
