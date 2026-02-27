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
	"bytes"
	"encoding/json"
	"fmt"
	"net/http"
	"time"
)

// --- Types for authservice REST API communication ---

type AuthLoginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

type AuthLoginResponse struct {
	Token     string `json:"token"`
	ExpiresAt int64  `json:"expires_at"`
	Username  string `json:"username"`
}

type AuthRegisterRequest struct {
	Email     string `json:"email"`
	Username  string `json:"username"`
	Password  string `json:"password"`
	FirstName string `json:"first_name"`
	LastName  string `json:"last_name"`
}

type AuthProfileResponse struct {
	UserID    string `json:"user_id"`
	Email     string `json:"email"`
	Username  string `json:"username"`
	FirstName string `json:"first_name"`
	LastName  string `json:"last_name"`
	CreatedAt string `json:"created_at"`
}

type AuthErrorResponse struct {
	Error string `json:"error"`
}

var authHTTPClient = &http.Client{
	Timeout: 5 * time.Second,
}

// authLogin calls authservice POST /api/login
func (fe *frontendServer) authLogin(email, password string) (*AuthLoginResponse, error) {
	body, _ := json.Marshal(AuthLoginRequest{Email: email, Password: password})
	resp, err := authHTTPClient.Post(
		fmt.Sprintf("http://%s/api/login", fe.authSvcAddr),
		"application/json",
		bytes.NewBuffer(body),
	)
	if err != nil {
		return nil, fmt.Errorf("auth service unavailable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errResp AuthErrorResponse
		json.NewDecoder(resp.Body).Decode(&errResp)
		if errResp.Error != "" {
			return nil, fmt.Errorf("%s", errResp.Error)
		}
		return nil, fmt.Errorf("login failed (status %d)", resp.StatusCode)
	}

	var result AuthLoginResponse
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode login response: %w", err)
	}
	return &result, nil
}

// authRegister calls authservice POST /api/register
func (fe *frontendServer) authRegister(req AuthRegisterRequest) error {
	body, _ := json.Marshal(req)
	resp, err := authHTTPClient.Post(
		fmt.Sprintf("http://%s/api/register", fe.authSvcAddr),
		"application/json",
		bytes.NewBuffer(body),
	)
	if err != nil {
		return fmt.Errorf("auth service unavailable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusCreated {
		var errResp AuthErrorResponse
		json.NewDecoder(resp.Body).Decode(&errResp)
		if errResp.Error != "" {
			return fmt.Errorf("%s", errResp.Error)
		}
		return fmt.Errorf("registration failed (status %d)", resp.StatusCode)
	}
	return nil
}

// authGetProfile calls authservice GET /api/profile with Bearer token
func (fe *frontendServer) authGetProfile(token string) (*AuthProfileResponse, error) {
	req, err := http.NewRequest("GET", fmt.Sprintf("http://%s/api/profile", fe.authSvcAddr), nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("Authorization", "Bearer "+token)

	resp, err := authHTTPClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("auth service unavailable: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("failed to get profile (status %d)", resp.StatusCode)
	}

	var profile AuthProfileResponse
	if err := json.NewDecoder(resp.Body).Decode(&profile); err != nil {
		return nil, fmt.Errorf("failed to decode profile response: %w", err)
	}
	return &profile, nil
}
