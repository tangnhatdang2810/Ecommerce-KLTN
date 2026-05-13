import math
import random
import uuid
from locust import HttpUser, task, between, LoadTestShape

class ShopperUser(HttpUser):
    # CHỈNH SỬA 1: Giảm wait_time để tăng RPS đáng kể
    # Từ (1, 4) xuống (0.5, 1.5) -> Ép mỗi user bắn request nhanh gấp đôi
    wait_time = between(0.5, 1.5) 

    def on_start(self):
        self.user_id = str(uuid.uuid4())
        self.product_ids = [
            "OLJCESPC7Z", "66VCHSJNUP", "1YMWWN1N4O", 
            "L9ECAV2TTE", "2ZYFJ3GM2N", "0PUK6V6EEO", 
            "LS4PSXUNUM", "9SIQT8TOJO", "6E92ZMYYFZ"
        ]

    @task(5)
    def browse_products(self):
        self.client.get("/api/products", name="/api/products")

    @task(3)
    def view_product(self):
        prod_id = random.choice(self.product_ids)
        self.client.get(f"/api/products/{prod_id}", name="/api/products/[id]")

    @task(2)
    def view_cart(self):
        self.client.get(f"/api/cart/{self.user_id}", name="/api/cart/[userId]")

    @task(1)
    def add_to_cart(self):
        prod_id = random.choice(self.product_ids)
        payload = {"productId": prod_id, "quantity": 1}
        self.client.post(f"/api/cart/{self.user_id}/items", json=payload, name="/api/cart/[userId]/items")

class LongRunningLoadShape(LoadTestShape):
    """
    Kịch bản 60 phút đã được "ép tải" để phục vụ DRL training
    """
    def tick(self):
        run_time = self.get_run_time()

        # 1. RAMP UP (0-10p): Tăng lên 60 users (tăng tải nền nhẹ)
        if run_time < 600:
            return (60, 1)

        # 2. STEADY STATE (10-25p): Giữ mức 60 users 
        # (Mức này với wait_time thấp sẽ bắt đầu làm CPU nóng lên)
        elif run_time < 1500:
            return (60, 0)

        # 3. MULTI-SPIKES (25-35p): Tăng vọt lên 150 users
        # CHỈNH SỬA 2: Nâng từ 120 lên 150 để chắc chắn vượt ngưỡng scale của 16GB RAM
        elif run_time < 2100:
            if (run_time // 300) % 2 == 0:
                return (150, 15) # Spike cực mạnh
            else:
                return (60, 10)

        # 4. LONG WAVE (35-50p): Sóng hình sin biên độ lớn
        # CHỈNH SỬA 3: Nâng đỉnh sóng lên 130 users
        elif run_time < 3000:
            amplitude = 50 
            mean_users = 80
            period = 300 
            users = int(mean_users + amplitude * math.sin(2 * math.pi * run_time / period))
            return (max(users, 40), 5)

        # 5. COOL DOWN (50-60p): Hạ nhanh về 10 để xem nó dọn dẹp Pod
        elif run_time < 3600:
            return (10, 2)

        return None