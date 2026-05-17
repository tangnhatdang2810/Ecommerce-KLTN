"""
SESSION 4: Mixed High Load
Mục tiêu: Thu data productcatalog với replicas 6-8 nhiều hơn
Pattern:
  0-5 phút:   5 users   (warmup)
  5-15 phút:  500 users (spike mạnh - ép product lên 6-8)
  15-20 phút: 5 users   (cool down)
  20-30 phút: 600 users (sustained high - ép lên max)
  30-35 phút: 5 users   (cool down)
  35-45 phút: 400 users (spike vừa)
  45-50 phút: 5 users   (cool down)
  50-60 phút: 5 users   (idle - observe scale down về 1)
"""

from locust import HttpUser, task, between, LoadTestShape
import random

API_GATEWAY = "http://192.168.123.40:30090"

TEST_ACCOUNTS = [
    {"email": "user1@test.com", "password": "password123"},
    {"email": "user2@test.com", "password": "password123"},
    {"email": "user3@test.com", "password": "password123"},
    {"email": "user4@test.com", "password": "password123"},
    {"email": "user5@test.com", "password": "password123"},
]


class SpikeShape(LoadTestShape):
    stages = [
        {"duration": 300,  "users": 5,   "spawn_rate": 5},    # 0-5p warmup
        {"duration": 900,  "users": 150, "spawn_rate": 30},   # 5-15p spike mạnh
        {"duration": 1200, "users": 5,   "spawn_rate": 30},   # 15-20p cool down
        {"duration": 1800, "users": 200, "spawn_rate": 30},   # 20-30p sustained high
        {"duration": 2100, "users": 5,   "spawn_rate": 30},   # 30-35p cool down
        {"duration": 2700, "users": 150, "spawn_rate": 30},    # 35-45p spike vừa
        {"duration": 3000, "users": 5,   "spawn_rate": 30},   # 45-50p cool down
        {"duration": 3600, "users": 5,   "spawn_rate": 5},     # 50-60p idle
    ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None


class ShopUser(HttpUser):
    host = API_GATEWAY
    wait_time = between(0.5, 2.0)

    token   = None
    user_id = None

    def on_start(self):
        account = random.choice(TEST_ACCOUNTS)
        for _ in range(3):
            self.login(account["email"], account["password"])
            if self.token:
                break

    def login(self, email: str, password: str):
        with self.client.post(
            "/api/login",
            json={"email": email, "password": password},
            catch_response=True,
            name="/api/login"
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                self.token   = data.get("token")
                self.user_id = data.get("username", email.split("@")[0])
                resp.success()
            else:
                resp.failure(f"Login failed: {resp.status_code}")
                self.token = None

    def auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    def browse_products(self):
        with self.client.get(
            "/api/products",
            headers=self.auth_headers(),
            catch_response=True,
            name="/api/products"
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    @task(8)  # Weight cao nhất → hit productcatalog nhiều nhất
    def view_product_detail(self):
        product_id = random.randint(1, 20)
        with self.client.get(
            f"/api/products/{product_id}",
            headers=self.auth_headers(),
            catch_response=True,
            name="/api/products/{id}"
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    @task(3)
    def view_cart(self):
        if not self.token:
            return
        with self.client.get(
            f"/api/cart/{self.user_id}",
            headers=self.auth_headers(),
            catch_response=True,
            name="/api/cart/{userId}"
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")

    @task(2)
    def add_to_cart(self):
        if not self.token:
            return
        product_id = random.randint(1, 20)
        with self.client.post(
            f"/api/cart/{self.user_id}/items",
            json={"productId": str(product_id), "quantity": random.randint(1, 3)},
            headers=self.auth_headers(),
            catch_response=True,
            name="/api/cart/{userId}/items"
        ) as resp:
            if resp.status_code in (200, 201):
                resp.success()
            else:
                resp.failure(f"{resp.status_code}")