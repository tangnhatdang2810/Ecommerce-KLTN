package main

// types.go defines the model types used across the frontend,
// replacing the protobuf-generated types from genproto/.

import (
	"github.com/GoogleCloudPlatform/microservices-demo/src/frontend/money"
)

// Product represents a product in the catalog.
type Product struct {
	Id          string       `json:"id"`
	Name        string       `json:"name"`
	Description string       `json:"description"`
	Picture     string       `json:"picture"`
	PriceUsd    *money.Money `json:"priceUsd"`
	Categories  []string     `json:"categories"`
}

// CartItem represents an item in the shopping cart.
type CartItem struct {
	ProductId string `json:"productId"`
	Quantity  int32  `json:"quantity"`
}

// Cart represents a user's shopping cart.
type Cart struct {
	UserId string      `json:"userId"`
	Items  []*CartItem `json:"items"`
}

// Address represents a shipping address.
type Address struct {
	StreetAddress string `json:"streetAddress"`
	City          string `json:"city"`
	State         string `json:"state"`
	Country       string `json:"country"`
	ZipCode       int32  `json:"zipCode"`
}

// CreditCardInfo represents credit card details.
type CreditCardInfo struct {
	CreditCardNumber          string `json:"creditCardNumber"`
	CreditCardCvv             int32  `json:"creditCardCvv"`
	CreditCardExpirationYear  int32  `json:"creditCardExpirationYear"`
	CreditCardExpirationMonth int32  `json:"creditCardExpirationMonth"`
}

// OrderItem represents a single item in an order.
type OrderItem struct {
	Item *CartItem    `json:"item"`
	Cost *money.Money `json:"cost"`
}

// OrderResult represents the result of a completed order.
type OrderResult struct {
	OrderId            string       `json:"orderId"`
	ShippingTrackingId string       `json:"shippingTrackingId"`
	ShippingCost       *money.Money `json:"shippingCost"`
	ShippingAddress    *Address     `json:"shippingAddress"`
	Items              []*OrderItem `json:"items"`
	UserId             string       `json:"userId"`
	Email              string       `json:"email"`
	TotalCost          *money.Money `json:"totalCost"`
	CreatedAt          string       `json:"createdAt"`
	UserCurrency       string       `json:"userCurrency"`
}

// PlaceOrderRequest represents a checkout request.
type PlaceOrderRequest struct {
	UserId       string          `json:"userId"`
	UserCurrency string          `json:"userCurrency"`
	Address      *Address        `json:"address"`
	Email        string          `json:"email"`
	CreditCard   *CreditCardInfo `json:"creditCard"`
}

// PlaceOrderResponse wraps an OrderResult.
type PlaceOrderResponse struct {
	Order *OrderResult `json:"order"`
}

// Ad is a placeholder since ad service was removed.
type Ad struct{}
