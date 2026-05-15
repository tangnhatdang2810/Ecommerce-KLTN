"""
SESSION 1: Tải ổn định (Constant Load)
- Mục tiêu: Thu data hệ thống hoạt động bình thường, ổn định
- Users: tăng dần lên 50, giữ nguyên suốt 1 giờ
- Chạy: locust -f session1_constant.py --headless -u 50 -r 5 --run-time 1h
"""

from locust import HttpUser, task, between
import random

API_GATEWAY = "http://192.168.123.40:30090"

TEST_ACCOUNTS = [
    {"email": "user1@test.com", "password": "password123"},
    {"email": "user2@test.com", "password": "password123"},
    {"email": "user3@test.com", "password": "password123"},
    {"email": "user4@test.com", "password": "password123"},
    {"email": "user5@test.com", "password": "password123"},
]


class ShopUser(HttpUser):
    host = API_GATEWAY
    wait_time = between(2, 5)

    token = None
    user_id = None

    def on_start(self):
        """Login 1 lần duy nhất khi user bắt đầu."""
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
                self.token = data.get("token")
                self.user_id = data.get("username", email.split("@")[0])
                resp.success()
            else:
                resp.failure(f"Login failed: {resp.status_code}")
                self.token = None

    def auth_headers(self) -> dict:
        if self.token:
            return {"Authorization": f"Bearer {self.token}"}
        return {}

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

    @task(3)
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