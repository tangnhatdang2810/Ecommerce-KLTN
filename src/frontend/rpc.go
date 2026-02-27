// Copyright 2018 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"

	"github.com/GoogleCloudPlatform/microservices-demo/src/frontend/money"
)

// Exchange rates relative to USD
var exchangeRates = map[string]float64{
	"USD": 1.0,
	"EUR": 0.92,
	"CAD": 1.37,
	"JPY": 154.70,
	"GBP": 0.79,
	"TRY": 34.25,
}

func (fe *frontendServer) getCurrencies(ctx context.Context) ([]string, error) {
	return []string{"USD", "EUR", "CAD", "JPY", "GBP", "TRY"}, nil
}

func (fe *frontendServer) getProducts(ctx context.Context) ([]*Product, error) {
	url := fmt.Sprintf("http://%s/api/products", fe.productCatalogSvcAddr)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("productcatalog: status %d: %s", resp.StatusCode, body)
	}
	var products []*Product
	if err := json.NewDecoder(resp.Body).Decode(&products); err != nil {
		return nil, err
	}
	return products, nil
}

func (fe *frontendServer) getProduct(ctx context.Context, id string) (*Product, error) {
	url := fmt.Sprintf("http://%s/api/products/%s", fe.productCatalogSvcAddr, id)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("productcatalog: status %d: %s", resp.StatusCode, body)
	}
	var product Product
	if err := json.NewDecoder(resp.Body).Decode(&product); err != nil {
		return nil, err
	}
	return &product, nil
}

func (fe *frontendServer) getCart(ctx context.Context, userID string) ([]*CartItem, error) {
	url := fmt.Sprintf("http://%s/api/cart/%s", fe.cartSvcAddr, userID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("cart: status %d: %s", resp.StatusCode, body)
	}
	var cart Cart
	if err := json.NewDecoder(resp.Body).Decode(&cart); err != nil {
		return nil, err
	}
	return cart.Items, nil
}

func (fe *frontendServer) emptyCart(ctx context.Context, userID string) error {
	url := fmt.Sprintf("http://%s/api/cart/%s", fe.cartSvcAddr, userID)
	req, err := http.NewRequestWithContext(ctx, http.MethodDelete, url, nil)
	if err != nil {
		return err
	}
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("cart: empty failed: status %d: %s", resp.StatusCode, body)
	}
	return nil
}

func (fe *frontendServer) updateCartItemQuantity(ctx context.Context, userID, productID string, quantity int32) error {
	cartURL := fmt.Sprintf("http://%s/api/cart/%s/items/%s", fe.cartSvcAddr, userID, productID)
	item := CartItem{ProductId: productID, Quantity: quantity}
	body, err := json.Marshal(item)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPut, cartURL, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("cart: update quantity failed: status %d: %s", resp.StatusCode, respBody)
	}
	return nil
}

func (fe *frontendServer) insertCart(ctx context.Context, userID, productID string, quantity int32) error {
	url := fmt.Sprintf("http://%s/api/cart/%s/items", fe.cartSvcAddr, userID)
	item := CartItem{ProductId: productID, Quantity: quantity}
	body, err := json.Marshal(item)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("cart: add item failed: status %d: %s", resp.StatusCode, respBody)
	}
	return nil
}

func (fe *frontendServer) convertCurrency(ctx context.Context, m *money.Money, currency string) (*money.Money, error) {
	if m.CurrencyCode == currency {
		return m, nil
	}
	// Convert source to USD first
	srcRate, ok := exchangeRates[m.CurrencyCode]
	if !ok {
		srcRate = 1.0
	}
	// Then from USD to target
	tgtRate, ok := exchangeRates[currency]
	if !ok {
		tgtRate = 1.0
	}
	// Calculate: total nanos in source, convert, split back
	totalNanos := float64(m.Units)*1e9 + float64(m.Nanos)
	converted := totalNanos / srcRate * tgtRate
	units := int64(converted / 1e9)
	nanos := int32(int64(converted) % 1e9)
	return &money.Money{
		CurrencyCode: currency,
		Units:        units,
		Nanos:        nanos,
	}, nil
}

func (fe *frontendServer) getShippingQuote(ctx context.Context, items []*CartItem, currency string) (*money.Money, error) {
	url := fmt.Sprintf("http://%s/api/shipping/quote", fe.shippingSvcAddr)
	reqBody := struct {
		Address interface{} `json:"address"`
		Items   []*CartItem `json:"items"`
	}{
		Address: nil,
		Items:   items,
	}
	body, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("shipping: quote failed: status %d: %s", resp.StatusCode, respBody)
	}
	var quoteResp struct {
		CostUsd *money.Money `json:"costUsd"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&quoteResp); err != nil {
		return nil, err
	}
	return quoteResp.CostUsd, nil
}

func (fe *frontendServer) placeOrder(ctx context.Context, orderReq *PlaceOrderRequest) (*PlaceOrderResponse, error) {
	url := fmt.Sprintf("http://%s/api/checkout", fe.checkoutSvcAddr)
	body, err := json.Marshal(orderReq)
	if err != nil {
		return nil, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, url, bytes.NewReader(body))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("checkout: place order failed: status %d: %s", resp.StatusCode, respBody)
	}
	var orderResp PlaceOrderResponse
	if err := json.NewDecoder(resp.Body).Decode(&orderResp); err != nil {
		return nil, err
	}
	return &orderResp, nil
}

func (fe *frontendServer) searchProducts(ctx context.Context, query string) ([]*Product, error) {
	searchURL := fmt.Sprintf("http://%s/api/products/search?q=%s", fe.productCatalogSvcAddr, url.QueryEscape(query))
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, searchURL, nil)
	if err != nil {
		return nil, err
	}
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("productcatalog: search failed: status %d: %s", resp.StatusCode, body)
	}
	var products []*Product
	if err := json.NewDecoder(resp.Body).Decode(&products); err != nil {
		return nil, err
	}
	return products, nil
}

func (fe *frontendServer) getRecommendations(ctx context.Context, userID string, productIDs []string) ([]*Product, error) {
	// Recommendation service removed — return empty
	return []*Product{}, nil
}

func (fe *frontendServer) getAd(ctx context.Context, ctxKeys []string) ([]*Ad, error) {
	// Ad service removed — return empty
	return []*Ad{}, nil
}

func (fe *frontendServer) getOrderHistory(ctx context.Context, userID string) ([]*OrderResult, error) {
	url := fmt.Sprintf("http://%s/api/checkout/orders/%s", fe.checkoutSvcAddr, userID)
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	resp, err := fe.httpClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		respBody, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("checkout: get order history failed: status %d: %s", resp.StatusCode, respBody)
	}
	var orders []*OrderResult
	if err := json.NewDecoder(resp.Body).Decode(&orders); err != nil {
		return nil, err
	}
	return orders, nil
}
