// Copyright 2024 Google LLC
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
	"net/http"

	"github.com/sirupsen/logrus"
)

const cookieToken = cookiePrefix + "token"
const cookieUsername = cookiePrefix + "username"

// loginPageHandler renders the login page (GET /login).
func (fe *frontendServer) loginPageHandler(w http.ResponseWriter, r *http.Request) {
	registered := r.URL.Query().Get("registered")
	data := map[string]interface{}{}
	if registered == "true" {
		data["success_message"] = "Registration successful! Please log in."
	}
	if err := templates.ExecuteTemplate(w, "login", injectCommonTemplateData(r, data)); err != nil {
		log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
		log.Error(err)
	}
}

// loginSubmitHandler handles the login form submission (POST /login).
func (fe *frontendServer) loginSubmitHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
	email := r.FormValue("email")
	password := r.FormValue("password")

	result, err := fe.authLogin(email, password)
	if err != nil {
		log.WithField("error", err).Warn("login failed")
		if templateErr := templates.ExecuteTemplate(w, "login", injectCommonTemplateData(r, map[string]interface{}{
			"login_error": err.Error(),
			"email":       email,
		})); templateErr != nil {
			log.Error(templateErr)
		}
		return
	}

	// Set JWT token cookie
	http.SetCookie(w, &http.Cookie{
		Name:   cookieToken,
		Value:  result.Token,
		MaxAge: cookieMaxAge,
		Path:   "/",
	})
	// Set username cookie for display purposes
	http.SetCookie(w, &http.Cookie{
		Name:   cookieUsername,
		Value:  result.Username,
		MaxAge: cookieMaxAge,
		Path:   "/",
	})

	log.WithField("username", result.Username).Info("user logged in successfully")

	// Migrate cart from anonymous session to logged-in user
	anonSessionID := sessionID(r)
	if anonSessionID != "" && anonSessionID != result.Username {
		anonCart, err := fe.getCart(r.Context(), anonSessionID)
		if err == nil && len(anonCart) > 0 {
			for _, item := range anonCart {
				if insertErr := fe.insertCart(r.Context(), result.Username, item.ProductId, item.Quantity); insertErr != nil {
					log.WithField("error", insertErr).Warn("failed to migrate cart item")
				}
			}
			// Clear the anonymous session cart
			_ = fe.emptyCart(r.Context(), anonSessionID)
			log.WithField("items", len(anonCart)).Info("migrated anonymous cart to user cart")
		}
	}

	w.Header().Set("Location", baseUrl+"/")
	w.WriteHeader(http.StatusFound)
}

// registerPageHandler renders the registration page (GET /register).
func (fe *frontendServer) registerPageHandler(w http.ResponseWriter, r *http.Request) {
	if err := templates.ExecuteTemplate(w, "register", injectCommonTemplateData(r, map[string]interface{}{})); err != nil {
		log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)
		log.Error(err)
	}
}

// registerSubmitHandler handles the registration form submission (POST /register).
func (fe *frontendServer) registerSubmitHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)

	req := AuthRegisterRequest{
		Email:     r.FormValue("email"),
		Username:  r.FormValue("username"),
		Password:  r.FormValue("password"),
		FirstName: r.FormValue("first_name"),
		LastName:  r.FormValue("last_name"),
	}

	if err := fe.authRegister(req); err != nil {
		log.WithField("error", err).Warn("registration failed")
		if templateErr := templates.ExecuteTemplate(w, "register", injectCommonTemplateData(r, map[string]interface{}{
			"register_error": err.Error(),
			"email":          req.Email,
			"username":       req.Username,
			"first_name":     req.FirstName,
			"last_name":      req.LastName,
		})); templateErr != nil {
			log.Error(templateErr)
		}
		return
	}

	log.WithField("email", req.Email).Info("user registered successfully")
	w.Header().Set("Location", baseUrl+"/login?registered=true")
	w.WriteHeader(http.StatusFound)
}

// profilePageHandler renders the user profile page (GET /profile).
func (fe *frontendServer) profilePageHandler(w http.ResponseWriter, r *http.Request) {
	log := r.Context().Value(ctxKeyLog{}).(logrus.FieldLogger)

	token := getAuthToken(r)
	if token == "" {
		w.Header().Set("Location", baseUrl+"/login")
		w.WriteHeader(http.StatusFound)
		return
	}

	profile, err := fe.authGetProfile(token)
	if err != nil {
		log.WithField("error", err).Warn("failed to get profile")
		// Token might be expired; clear cookies and redirect to login
		clearAuthCookies(w)
		w.Header().Set("Location", baseUrl+"/login")
		w.WriteHeader(http.StatusFound)
		return
	}

	if err := templates.ExecuteTemplate(w, "profile", injectCommonTemplateData(r, map[string]interface{}{
		"profile": profile,
	})); err != nil {
		log.Error(err)
	}
}

// authLogoutHandler clears auth cookies and redirects to home (GET /auth/logout).
func (fe *frontendServer) authLogoutHandler(w http.ResponseWriter, r *http.Request) {
	clearAuthCookies(w)
	w.Header().Set("Location", baseUrl+"/")
	w.WriteHeader(http.StatusFound)
}

// --- Helper functions ---

func getAuthToken(r *http.Request) string {
	c, err := r.Cookie(cookieToken)
	if err != nil {
		return ""
	}
	return c.Value
}

func getAuthUsername(r *http.Request) string {
	c, err := r.Cookie(cookieUsername)
	if err != nil {
		return ""
	}
	return c.Value
}

func isLoggedIn(r *http.Request) bool {
	return getAuthToken(r) != ""
}

func clearAuthCookies(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:   cookieToken,
		Value:  "",
		MaxAge: -1,
		Path:   "/",
	})
	http.SetCookie(w, &http.Cookie{
		Name:   cookieUsername,
		Value:  "",
		MaxAge: -1,
		Path:   "/",
	})
}
