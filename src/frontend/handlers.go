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
	"context"
	"encoding/json"
	"fmt"
	"html/template"
	"net"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gorilla/mux"
	"github.com/pkg/errors"
	"github.com/sirupsen/logrus"

	"github.com/GoogleCloudPlatform/microservices-demo/src/frontend/money"
	"github.com/GoogleCloudPlatform/microservices-demo/src/frontend/validator"
)

type platformDetails struct {
	css      string
	provider string
}

var (
	frontendMessage  = strings.TrimSpace(os.Getenv("FRONTEND_MESSAGE"))
	isCymbalBrand    = "true" == strings.ToLower(os.Getenv("CYMBAL_BRANDING"))
	templates        = template.Must(template.New("").
				Funcs(template.FuncMap{
			"renderMoney":        renderMoney,
			"renderCurrencyLogo": renderCurrencyLogo,
			"add": func(a, b int32) int32 { return a + b },
		}).ParseGlob("templates/*.html"))
	plat platformDetails
)

var validEnvs = []string{"local", "gcp", "azure", "aws", "onprem", "alibaba"}

func (fe *frontendServer) homeHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	log.WithField("currency", currentCurrency(r)).Info("home")
	currencies, err := fe.getCurrencies(r.Context())
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve currencies"), http.StatusInternalServerError)
		return
	}
	products, err := fe.getProducts(r.Context())
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve products"), http.StatusInternalServerError)
		return
	}
	cart, err := fe.getCart(r.Context(), cartUserID(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve cart"), http.StatusInternalServerError)
		return
	}

	type productView struct {
		Item  *Product
		Price *money.Money
	}
	ps := make([]productView, len(products))
	for i, p := range products {
		price, err := fe.convertCurrency(r.Context(), p.PriceUsd, currentCurrency(r))
		if err != nil {
			renderHTTPError(log, r, w, errors.Wrapf(err, "failed to do currency conversion for product %s", p.Id), http.StatusInternalServerError)
			return
		}
		ps[i] = productView{p, price}
	}

	// Set ENV_PLATFORM (default to local if not set; use env var if set; otherwise detect GCP, which overrides env)_
	var env = os.Getenv("ENV_PLATFORM")
	// Only override from env variable if set + valid env
	if env == "" || stringinSlice(validEnvs, env) == false {
		fmt.Println("env platform is either empty or invalid")
		env = "local"
	}
	// Autodetect GCP
	addrs, err := net.LookupHost("metadata.google.internal.")
	if err == nil && len(addrs) >= 0 {
		log.Debugf("Detected Google metadata server: %v, setting ENV_PLATFORM to GCP.", addrs)
		env = "gcp"
	}

	log.Debugf("ENV_PLATFORM is: %s", env)
	plat = platformDetails{}
	plat.setPlatformDetails(strings.ToLower(env))

	if err := templates.ExecuteTemplate(w, "home", injectCommonTemplateData(r, map[string]interface{}{
		"show_currency": true,
		"currencies":    currencies,
		"products":      ps,
		"cart_size":     cartSize(cart),
		"banner_color":  os.Getenv("BANNER_COLOR"), // illustrates canary deployments
	})); err != nil {
		log.Error(err)
	}
}

func (plat *platformDetails) setPlatformDetails(env string) {
	if env == "aws" {
		plat.provider = "AWS"
		plat.css = "aws-platform"
	} else if env == "onprem" {
		plat.provider = "On-Premises"
		plat.css = "onprem-platform"
	} else if env == "azure" {
		plat.provider = "Azure"
		plat.css = "azure-platform"
	} else if env == "gcp" {
		plat.provider = "Google Cloud"
		plat.css = "gcp-platform"
	} else if env == "alibaba" {
		plat.provider = "Alibaba Cloud"
		plat.css = "alibaba-platform"
	} else {
		plat.provider = "local"
		plat.css = "local"
	}
}

func (fe *frontendServer) productHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	id := mux.Vars(r)["id"]
	if id == "" {
		renderHTTPError(log, r, w, errors.New("product id not specified"), http.StatusBadRequest)
		return
	}
	log.WithField("id", id).WithField("currency", currentCurrency(r)).
		Debug("serving product page")

	p, err := fe.getProduct(r.Context(), id)
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve product"), http.StatusInternalServerError)
		return
	}
	currencies, err := fe.getCurrencies(r.Context())
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve currencies"), http.StatusInternalServerError)
		return
	}

	cart, err := fe.getCart(r.Context(), cartUserID(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve cart"), http.StatusInternalServerError)
		return
	}

	price, err := fe.convertCurrency(r.Context(), p.PriceUsd, currentCurrency(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to convert currency"), http.StatusInternalServerError)
		return
	}

	// ignores the error retrieving recommendations since it is not critical
	recommendations, err := fe.getRecommendations(r.Context(), sessionID(r), []string{id})
	if err != nil {
		log.WithField("error", err).Warn("failed to get product recommendations")
	}

	product := struct {
		Item  *Product
		Price *money.Money
	}{p, price}

	// Fetch packaging info (weight/dimensions) of the product
	// The packaging service is an optional microservice you can run as part of a Google Cloud demo.
	var packagingInfo *PackagingInfo = nil
	if isPackagingServiceConfigured() {
		packagingInfo, err = httpGetPackagingInfo(id)
		if err != nil {
			fmt.Println("Failed to obtain product's packaging info:", err)
		}
	}

	if err := templates.ExecuteTemplate(w, "product", injectCommonTemplateData(r, map[string]interface{}{
		"show_currency":   true,
		"currencies":      currencies,
		"product":         product,
		"recommendations": recommendations,
		"cart_size":       cartSize(cart),
		"packagingInfo":   packagingInfo,
	})); err != nil {
		log.Println(err)
	}
}

func (fe *frontendServer) addToCartHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	quantity, _ := strconv.ParseUint(r.FormValue("quantity"), 10, 32)
	productID := r.FormValue("product_id")
	payload := validator.AddToCartPayload{
		Quantity:  quantity,
		ProductID: productID,
	}
	if err := payload.Validate(); err != nil {
		renderHTTPError(log, r, w, validator.ValidationErrorResponse(err), http.StatusUnprocessableEntity)
		return
	}
	log.WithField("product", payload.ProductID).WithField("quantity", payload.Quantity).Debug("adding to cart")

	p, err := fe.getProduct(r.Context(), payload.ProductID)
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve product"), http.StatusInternalServerError)
		return
	}

	if err := fe.insertCart(r.Context(), cartUserID(r), p.Id, int32(payload.Quantity)); err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to add to cart"), http.StatusInternalServerError)
		return
	}
	w.Header().Set("location", baseUrl + "/cart")
	w.WriteHeader(http.StatusFound)
}

func (fe *frontendServer) emptyCartHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	log.Debug("emptying cart")

	if err := fe.emptyCart(r.Context(), cartUserID(r)); err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to empty cart"), http.StatusInternalServerError)
		return
	}
	w.Header().Set("location", baseUrl + "/")
	w.WriteHeader(http.StatusFound)
}

func (fe *frontendServer) updateCartItemHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	productID := r.FormValue("product_id")
	quantityStr := r.FormValue("quantity")
	quantity, err := strconv.ParseInt(quantityStr, 10, 32)
	if err != nil || productID == "" {
		renderHTTPError(log, r, w, errors.New("invalid product_id or quantity"), http.StatusBadRequest)
		return
	}
	log.WithField("product_id", productID).WithField("quantity", quantity).Debug("updating cart item quantity")

	if err := fe.updateCartItemQuantity(r.Context(), cartUserID(r), productID, int32(quantity)); err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to update cart item"), http.StatusInternalServerError)
		return
	}
	w.Header().Set("location", baseUrl+"/cart")
	w.WriteHeader(http.StatusFound)
}

func (fe *frontendServer) viewCartHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	log.Debug("view user cart")
	currencies, err := fe.getCurrencies(r.Context())
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve currencies"), http.StatusInternalServerError)
		return
	}
	cart, err := fe.getCart(r.Context(), cartUserID(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve cart"), http.StatusInternalServerError)
		return
	}

	// ignores the error retrieving recommendations since it is not critical
	recommendations, err := fe.getRecommendations(r.Context(), cartUserID(r), cartIDs(cart))
	if err != nil {
		log.WithField("error", err).Warn("failed to get product recommendations")
	}

	shippingCost, err := fe.getShippingQuote(r.Context(), cart, currentCurrency(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to get shipping quote"), http.StatusInternalServerError)
		return
	}

	// Convert shipping cost to user's selected currency
	shippingCost, err = fe.convertCurrency(r.Context(), shippingCost, currentCurrency(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to convert shipping cost currency"), http.StatusInternalServerError)
		return
	}

	type cartItemView struct {
		Item     *Product
		Quantity int32
		Price    *money.Money
	}
	items := make([]cartItemView, len(cart))
	totalPrice := money.Money{CurrencyCode: currentCurrency(r)}
	for i, item := range cart {
		p, err := fe.getProduct(r.Context(), item.ProductId)
		if err != nil {
			renderHTTPError(log, r, w, errors.Wrapf(err, "could not retrieve product #%s", item.ProductId), http.StatusInternalServerError)
			return
		}
		price, err := fe.convertCurrency(r.Context(), p.PriceUsd, currentCurrency(r))
		if err != nil {
			renderHTTPError(log, r, w, errors.Wrapf(err, "could not convert currency for product #%s", item.ProductId), http.StatusInternalServerError)
			return
		}

		multPrice := money.MultiplySlow(*price, uint32(item.Quantity))
		items[i] = cartItemView{
			Item:     p,
			Quantity: item.Quantity,
			Price:    &multPrice}
		totalPrice = money.Must(money.Sum(totalPrice, multPrice))
	}
	totalPrice = money.Must(money.Sum(totalPrice, *shippingCost))
	year := time.Now().Year()

	if err := templates.ExecuteTemplate(w, "cart", injectCommonTemplateData(r, map[string]interface{}{
		"currencies":       currencies,
		"recommendations":  recommendations,
		"cart_size":        cartSize(cart),
		"shipping_cost":    shippingCost,
		"show_currency":    true,
		"total_cost":       totalPrice,
		"items":            items,
		"expiration_years": []int{year, year + 1, year + 2, year + 3, year + 4},
	})); err != nil {
		log.Println(err)
	}
}

func (fe *frontendServer) placeOrderHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	log.Debug("placing order")

	// Require login to place order
	if !isLoggedIn(r) {
		w.Header().Set("Location", baseUrl+"/login")
		w.WriteHeader(http.StatusFound)
		return
	}

	var (
		email         = r.FormValue("email")
		streetAddress = r.FormValue("street_address")
		zipCode, _    = strconv.ParseInt(r.FormValue("zip_code"), 10, 32)
		city          = r.FormValue("city")
		state         = r.FormValue("state")
		country       = r.FormValue("country")
		ccNumber      = r.FormValue("credit_card_number")
		ccMonth, _    = strconv.ParseInt(r.FormValue("credit_card_expiration_month"), 10, 32)
		ccYear, _     = strconv.ParseInt(r.FormValue("credit_card_expiration_year"), 10, 32)
		ccCVV, _      = strconv.ParseInt(r.FormValue("credit_card_cvv"), 10, 32)
	)

	payload := validator.PlaceOrderPayload{
		Email:         email,
		StreetAddress: streetAddress,
		ZipCode:       zipCode,
		City:          city,
		State:         state,
		Country:       country,
		CcNumber:      ccNumber,
		CcMonth:       ccMonth,
		CcYear:        ccYear,
		CcCVV:         ccCVV,
	}
	if err := payload.Validate(); err != nil {
		renderHTTPError(log, r, w, validator.ValidationErrorResponse(err), http.StatusUnprocessableEntity)
		return
	}

	order, err := fe.placeOrder(r.Context(), &PlaceOrderRequest{
		Email: payload.Email,
		CreditCard: &CreditCardInfo{
			CreditCardNumber:          payload.CcNumber,
			CreditCardExpirationMonth: int32(payload.CcMonth),
			CreditCardExpirationYear:  int32(payload.CcYear),
			CreditCardCvv:             int32(payload.CcCVV)},
		UserId:       cartUserID(r),
		UserCurrency: currentCurrency(r),
		Address: &Address{
			StreetAddress: payload.StreetAddress,
			City:          payload.City,
			State:         payload.State,
			ZipCode:       int32(payload.ZipCode),
			Country:       payload.Country},
	})
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "failed to complete the order"), http.StatusInternalServerError)
		return
	}
	log.WithField("order", order.Order.OrderId).Info("order placed")

	recommendations, _ := fe.getRecommendations(r.Context(), sessionID(r), nil)

	totalPaid := *order.Order.ShippingCost
	for _, v := range order.Order.Items {
		multPrice := money.MultiplySlow(*v.Cost, uint32(v.Item.Quantity))
		totalPaid = money.Must(money.Sum(totalPaid, multPrice))
	}

	// Convert totalPaid to user's selected currency
	userCur := currentCurrency(r)
	if userCur != "USD" {
		if converted, err := fe.convertCurrency(r.Context(), &totalPaid, userCur); err == nil {
			totalPaid = *converted
		}
	}

	currencies, err := fe.getCurrencies(r.Context())
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve currencies"), http.StatusInternalServerError)
		return
	}

	if err := templates.ExecuteTemplate(w, "order", injectCommonTemplateData(r, map[string]interface{}{
		"show_currency":   false,
		"currencies":      currencies,
		"order":           order.Order,
		"total_paid":      &totalPaid,
		"recommendations": recommendations,
	})); err != nil {
		log.Println(err)
	}
}

func (fe *frontendServer) logoutHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	log.Debug("logging out")
	for _, c := range r.Cookies() {
		c.Expires = time.Now().Add(-time.Hour * 24 * 365)
		c.MaxAge = -1
		http.SetCookie(w, c)
	}
	w.Header().Set("Location", baseUrl + "/")
	w.WriteHeader(http.StatusFound)
}

func (fe *frontendServer) getProductByID(w http.ResponseWriter, r *http.Request) {
	id := mux.Vars(r)["ids"]
	if id == "" {
		return
	}

	p, err := fe.getProduct(r.Context(), id)
	if err != nil {
		return
	}

	jsonData, err := json.Marshal(p)
	if err != nil {
		fmt.Println(err)
		return
	}

	w.Write(jsonData)
	w.WriteHeader(http.StatusOK)
}

func (fe *frontendServer) setCurrencyHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	cur := r.FormValue("currency_code")
	payload := validator.SetCurrencyPayload{Currency: cur}
	if err := payload.Validate(); err != nil {
		renderHTTPError(log, r, w, validator.ValidationErrorResponse(err), http.StatusUnprocessableEntity)
		return
	}
	log.WithField("curr.new", payload.Currency).WithField("curr.old", currentCurrency(r)).
		Debug("setting currency")

	if payload.Currency != "" {
		http.SetCookie(w, &http.Cookie{
			Name:   cookieCurrency,
			Value:  payload.Currency,
			MaxAge: cookieMaxAge,
		})
	}
	referer := r.Header.Get("referer")
	if referer == "" {
		referer = baseUrl + "/"
	}
	w.Header().Set("Location", referer)
	w.WriteHeader(http.StatusFound)
}

// chooseAd is a no-op since ad service was removed.
func (fe *frontendServer) chooseAd(ctx context.Context, ctxKeys []string, log logrus.FieldLogger) *Ad {
	return nil
}

func renderHTTPError(log logrus.FieldLogger, r *http.Request, w http.ResponseWriter, err error, code int) {
	log.WithField("error", err).Error("request error")
	errMsg := fmt.Sprintf("%+v", err)

	w.WriteHeader(code)

	if templateErr := templates.ExecuteTemplate(w, "error", injectCommonTemplateData(r, map[string]interface{}{
		"error":       errMsg,
		"status_code": code,
		"status":      http.StatusText(code),
	})); templateErr != nil {
		log.Println(templateErr)
	}
}

func injectCommonTemplateData(r *http.Request, payload map[string]interface{}) map[string]interface{} {
	data := map[string]interface{}{
		"session_id":        sessionID(r),
		"request_id":        r.Context().Value(ctxKeyRequestID{}),
		"user_currency":     currentCurrency(r),
		"platform_css":      plat.css,
		"platform_name":     plat.provider,
		"is_cymbal_brand":   isCymbalBrand,
		"deploymentDetails": deploymentDetailsMap,
		"frontendMessage":   frontendMessage,
		"currentYear":       time.Now().Year(),
		"baseUrl":           baseUrl,
		"logged_in":         isLoggedIn(r),
		"username":          getAuthUsername(r),
	}

	for k, v := range payload {
		data[k] = v
	}

	return data
}

func currentCurrency(r *http.Request) string {
	c, _ := r.Cookie(cookieCurrency)
	if c != nil {
		return c.Value
	}
	return defaultCurrency
}

func sessionID(r *http.Request) string {
	v := r.Context().Value(ctxKeySessionID{})
	if v != nil {
		return v.(string)
	}
	return ""
}

// cartUserID returns the username if logged in, otherwise falls back to sessionID.
// This ensures cart and order operations use a consistent user identifier.
func cartUserID(r *http.Request) string {
	if u := getAuthUsername(r); u != "" {
		return u
	}
	return sessionID(r)
}

func cartIDs(c []*CartItem) []string {
	out := make([]string, len(c))
	for i, v := range c {
		out[i] = v.ProductId
	}
	return out
}

// get total # of items in cart
func cartSize(c []*CartItem) int {
	cartSize := 0
	for _, item := range c {
		cartSize += int(item.Quantity)
	}
	return cartSize
}

func renderMoney(m money.Money) string {
	currencyLogo := renderCurrencyLogo(m.CurrencyCode)
	return fmt.Sprintf("%s%d.%02d", currencyLogo, m.Units, m.Nanos/10000000)
}

func renderCurrencyLogo(currencyCode string) string {
	logos := map[string]string{
		"USD": "$",
		"CAD": "$",
		"JPY": "¥",
		"EUR": "€",
		"TRY": "₺",
		"GBP": "£",
	}

	logo := "$" //default
	if val, ok := logos[currencyCode]; ok {
		logo = val
	}
	return logo
}

func (fe *frontendServer) searchHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	query := r.URL.Query().Get("q")
	log.WithField("query", query).Info("search")

	currencies, err := fe.getCurrencies(r.Context())
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve currencies"), http.StatusInternalServerError)
		return
	}

	cart, err := fe.getCart(r.Context(), cartUserID(r))
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve cart"), http.StatusInternalServerError)
		return
	}

	var products []*Product
	if query != "" {
		products, err = fe.searchProducts(r.Context(), query)
		if err != nil {
			log.WithField("error", err).Warn("search failed, returning empty results")
			products = []*Product{}
		}
	}

	type productView struct {
		Item  *Product
		Price *money.Money
	}
	ps := make([]productView, len(products))
	for i, p := range products {
		price, err := fe.convertCurrency(r.Context(), p.PriceUsd, currentCurrency(r))
		if err != nil {
			renderHTTPError(log, r, w, errors.Wrapf(err, "failed currency conversion for product %s", p.Id), http.StatusInternalServerError)
			return
		}
		ps[i] = productView{p, price}
	}

	if err := templates.ExecuteTemplate(w, "search", injectCommonTemplateData(r, map[string]interface{}{
		"show_currency": true,
		"currencies":    currencies,
		"products":      ps,
		"query":         query,
		"result_count":  len(ps),
		"cart_size":     cartSize(cart),
	})); err != nil {
		log.Error(err)
	}
}

func stringinSlice(slice []string, val string) bool {
	for _, item := range slice {
		if item == val {
			return true
		}
	}
	return false
}

func (fe *frontendServer) orderHistoryHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	log.Debug("view order history")

	// Require login to view order history
	username := getAuthUsername(r)
	if username == "" {
		w.Header().Set("Location", baseUrl+"/login")
		w.WriteHeader(http.StatusFound)
		return
	}

	orders, err := fe.getOrderHistory(r.Context(), username)
	if err != nil {
		renderHTTPError(log, r, w, errors.Wrap(err, "could not retrieve order history"), http.StatusInternalServerError)
		return
	}

	// For each order, resolve product names and convert currency for display
	type orderItemView struct {
		ProductName string
		ProductId   string
		Quantity    int32
		Cost        money.Money
	}
	type orderView struct {
		OrderId            string
		ShippingTrackingId string
		ShippingCost       money.Money
		TotalCost          money.Money
		Items              []orderItemView
		CreatedAt          string
	}

	var orderViews []orderView
	for _, o := range orders {
		// Determine the currency used for this order
		orderCurrency := o.UserCurrency
		if orderCurrency == "" {
			orderCurrency = "USD"
		}

		sc := money.Money{}
		if o.ShippingCost != nil {
			sc = *o.ShippingCost
		}
		tc := money.Money{}
		if o.TotalCost != nil {
			tc = *o.TotalCost
		}

		// Convert shipping cost and total from USD to the order's currency
		if orderCurrency != "USD" {
			if converted, err := fe.convertCurrency(r.Context(), &sc, orderCurrency); err == nil {
				sc = *converted
			}
			if converted, err := fe.convertCurrency(r.Context(), &tc, orderCurrency); err == nil {
				tc = *converted
			}
		}

		ov := orderView{
			OrderId:            o.OrderId,
			ShippingTrackingId: o.ShippingTrackingId,
			ShippingCost:       sc,
			TotalCost:          tc,
			CreatedAt:          o.CreatedAt,
		}
		for _, item := range o.Items {
			c := money.Money{}
			if item.Cost != nil {
				c = *item.Cost
			}
			// Convert item cost from USD to order's currency
			if orderCurrency != "USD" {
				if converted, err := fe.convertCurrency(r.Context(), &c, orderCurrency); err == nil {
					c = *converted
				}
			}
			iv := orderItemView{
				ProductId: item.Item.ProductId,
				Quantity:  item.Item.Quantity,
				Cost:      c,
			}
			// Try to get product name
			p, err := fe.getProduct(r.Context(), item.Item.ProductId)
			if err == nil && p != nil {
				iv.ProductName = p.Name
			} else {
				iv.ProductName = item.Item.ProductId
			}
			ov.Items = append(ov.Items, iv)
		}
		orderViews = append(orderViews, ov)
	}

	if err := templates.ExecuteTemplate(w, "order_history", injectCommonTemplateData(r, map[string]interface{}{
		"orders": orderViews,
	})); err != nil {
		log.Error(err)
	}
}
