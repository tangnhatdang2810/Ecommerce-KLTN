package hipstershop.model;

public class ShipResponse {
    private String trackingId;

    public ShipResponse() {}

    public ShipResponse(String trackingId) {
        this.trackingId = trackingId;
    }

    public String getTrackingId() { return trackingId; }
    public void setTrackingId(String trackingId) { this.trackingId = trackingId; }
}
