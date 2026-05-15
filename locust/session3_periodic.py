"""
SESSION 3: Tải theo chu kỳ (Periodic / Sine Wave Load)
- Mục tiêu: Thu data hệ thống với tải tăng giảm dần đều như sóng sin
- Pattern: dao động từ 5 → 80 users theo chu kỳ 15 phút
- Chạy: locust -f session3_periodic.py --headless -u 80 -r 10 --run-time 1h
"""

from locust import HttpUser, task, between, LoadTestShape
import math
import random


API_GATEWAY = "http://192.168.123.40:30090"

TEST_ACCOUNTS = [
    {"email": "user1@test.com", "password": "password123"},
    {"email": "user2@test.com", "password": "password123"},
    {"email": "user3@test.com", "password": "password123"},
    {"email": "user4@test.com", "password": "password123"},
    {"email": "user5@test.com", "password": "password123"},
]


class SineWaveShape(LoadTestShape):
    """
    Pattern tải dạng sóng sin:
    - Min users: 5
    - Max users: 80
    - Chu kỳ: 15 phút (900 giây)
    - Tổng thời gian: 1 giờ = 4 chu kỳ
    """

    MIN_USERS = 5
    MAX_USERS = 80
    PERIOD    = 900    # 15 phút
    TOTAL     = 3600   # 1 giờ

    def tick(self):
        run_time = self.get_run_time()
        if run_time > self.TOTAL:
            return None

        sine = math.sin(2 * math.pi * run_time / self.PERIOD - math.pi / 2)
        amplitude = (self.MAX_USERS - self.MIN_USERS) / 2
        mid = (self.MAX_USERS + self.MIN_USERS) / 2
        users = int(mid + amplitude * sine)
        users = max(self.MIN_USERS, min(self.MAX_USERS, users))

        current = self.get_current_user_count()
        spawn_rate = max(1, abs(users - current) // 5 + 1)
        return users, spawn_rate


class ShopUser(HttpUser):
    host = API_GATEWAY
    wait_time = between(0.5, 1.5)

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