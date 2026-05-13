import requests
import pandas as pd
import time
import os
import math
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

# ================= CẤU HÌNH =================
PROMETHEUS_URL = "http://192.168.123.30:30830" # <-- Kiểm tra lại IP này
OUTPUT_PATH    = "raw_metrics.csv"
STEP_SECONDS   = 15
NAMESPACE      = "app"

SERVICES = {
    "apigateway": "apigateway",
    "productcatalog": "productcatalogservice",
    "cartservice": "cartservice",
}

# ================= QUERIES (Đã tối ưu nhãn) =================
def get_service_queries(svc_key, deploy_name):
    # Dùng service_name để lọc vì Grafana của bạn dùng nhãn này
    return {
        "cpu": f'avg(rate(container_cpu_usage_seconds_total{{namespace="{NAMESPACE}", pod=~"{deploy_name}-.*"}}[1m])) * 100',
        "memory": f'avg(container_memory_working_set_bytes{{namespace="{NAMESPACE}", pod=~"{deploy_name}-.*"}}) / avg(kube_pod_container_resource_limits{{namespace="{NAMESPACE}", resource="memory", pod=~"{deploy_name}-.*"}}) * 100',
        "latency_p95": f'histogram_quantile(0.95, sum(rate(http_server_requests_seconds_bucket{{namespace="{NAMESPACE}", service=~"{deploy_name}.*"}}[1m])) by (le)) * 1000',
        "rps": f'sum(rate(http_server_requests_seconds_count{{namespace="{NAMESPACE}", service=~"{deploy_name}.*", uri!~".*actuator.*"}}[1m]))',
        "replicas": f'kube_deployment_status_replicas_available{{namespace="{NAMESPACE}", deployment="{deploy_name}"}}',
        "error_rate": f'sum(rate(http_server_requests_seconds_count{{namespace="{NAMESPACE}", service=~"{deploy_name}.*", status=~"5.."}}[1m])) / clamp_min(sum(rate(http_server_requests_seconds_count{{namespace="{NAMESPACE}", service=~"{deploy_name}.*"}}[1m])), 1e-6)'
    }

def query_prom(name, query):
    try:
        r = requests.get(f"{PROMETHEUS_URL}/api/v1/query", params={"query": query}, timeout=3)
        res = r.json()
        if res["status"] == "success" and res["data"]["result"]:
            val = float(res["data"]["result"][0]["value"][1])
            return name, (round(val, 4) if not math.isnan(val) else 0.0)
        return name, 0.0
    except:
        return name, 0.0

def collect_step():
    all_queries = {}
    for skey, dname in SERVICES.items():
        svc_queries = get_service_queries(skey, dname)
        for mname, q in svc_queries.items():
            all_queries[f"{skey}_{mname}"] = q

    # Chạy SONG SONG toàn bộ 18 query cùng lúc (mất ~1s thay vì 15s)
    row = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(query_prom, k, q) for k, q in all_queries.items()]
        for f in futures:
            k, v = f.result()
            row[k] = v
    return row

# ================= LOOP CHÍNH =================
print(f"🚀 Đang thu thập... Lưu tại: {OUTPUT_PATH}")
data_list = []

try:
    while True:
        t1 = time.time()
        row = collect_step()
        data_list.append(row)
        
        # In nhanh kết quả để check
        print(f"[{row['timestamp']}] API_RPS: {row['apigateway_rps']:.2f} | Cart_CPU: {row['cartservice_cpu']:.1f}% | Pods: {row['apigateway_replicas']}")
        
        # Lưu định kỳ
        if len(data_list) % 5 == 0:
            pd.DataFrame(data_list).to_csv(OUTPUT_PATH, index=False)

        # Nghỉ bù trừ (Sẽ hết lag vì query chỉ mất 1s)
        elapsed = time.time() - t1
        time.sleep(max(0, STEP_SECONDS - elapsed))
except KeyboardInterrupt:
    pd.DataFrame(data_list).to_csv(OUTPUT_PATH, index=False)
    print("✅ Đã lưu data thành công!")