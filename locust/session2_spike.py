"""
SESSION 2: Tải tăng đột biến (Spike Load)
- Mục tiêu: Thu data hệ thống khi bị spike tải bất ngờ
- Pattern: thấp (5) → đột biến (200) → về thấp (5) → lặp lại
- Chạy: locust -f session2_spike.py --headless -u 200 -r 100 --run-time 1h
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
    """
    Pattern tải đột biến:
    - 0-5 phút:   5 users   (warm up)
    - 5-10 phút:  200 users (spike)
    - 10-15 phút: 5 users   (cool down)
    - 15-20 phút: 5 users   (ổn định thấp)
    - ... lặp lại 3 chu kỳ trong 1 giờ
    """

    stages = []

    def __init__(self):
        super().__init__()
        for cycle in range(3):
            base = cycle * 1200
            self.stages += [
                {"duration": base + 300,  "users": 5,   "spawn_rate": 5},
                {"duration": base + 600,  "users": 200, "spawn_rate": 100},
                {"duration": base + 900,  "users": 5,   "spawn_rate": 100},
                {"duration": base + 1200, "users": 5,   "spawn_rate": 5},
            ]

    def tick(self):
        run_time = self.get_run_time()
        for stage in self.stages:
            if run_time < stage["duration"]:
                return stage["users"], stage["spawn_rate"]
        return None


class ShopUser(HttpUser):
    host = API_GATEWAY
    wait_time = between(0.1, 0.5)

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