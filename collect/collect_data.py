"""
Script thu thập metrics từ Prometheus cho 4 services:
- cartservice
- productcatalogservice
- apigateway
- authservice

Metrics thu thập: cpu, memory, latency, rps, replicas, delta_rps
Interval: 15 giây
Output: CSV riêng cho từng service
"""

import requests
import csv
import time
import os
import signal
import sys
from datetime import datetime

# ===================== CẤU HÌNH =====================
PROMETHEUS_URL = "http://192.168.123.30:30830"
NAMESPACE = "app"
INTERVAL = 15  # giây

SERVICES = ["cartservice", "productcatalogservice", "apigateway"]

OUTPUT_DIR = "data/session4"  # đổi cho mỗi session
# session1: "data/session1_constant"
# session2: "data/session2_spike", "data/session2_spike_extra"
# session3: "data/session3_periodic"
# ====================================================


def query_prometheus(promql: str) -> float | None:
    try:
        resp = requests.get(
            f"{PROMETHEUS_URL}/api/v1/query",
            params={"query": promql},
            timeout=5
        )
        data = resp.json()
        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
        return None
    except Exception as e:
        print(f"  [WARN] Query failed: {e}")
        return None


def build_queries(service: str) -> dict:
    cpu = (
        f'sum(rate(container_cpu_usage_seconds_total{{'
        f'namespace="{NAMESPACE}", '
        f'pod=~"{service}.*", '
        f'container!=""'
        f'}}[1m]))'
    )
    memory = (
        f'sum(container_memory_working_set_bytes{{'
        f'namespace="{NAMESPACE}", '
        f'pod=~"{service}.*", '
        f'container!=""'
        f'}})'
    )
    replicas = (
        f'kube_deployment_status_replicas{{'
        f'namespace="{NAMESPACE}", '
        f'deployment="{service}"'
        f'}}'
    )

    # apigateway: uri=UNKNOWN nen KHONG filter uri
    # con lai: loai tru /actuator
    if service == "apigateway":
        rps = (
            f'sum(rate(http_server_requests_seconds_count{{'
            f'namespace="{NAMESPACE}", '
            f'service="{service}"'
            f'}}[1m]))'
        )
        latency = (
            f'histogram_quantile(0.95, sum(rate('
            f'http_server_requests_seconds_bucket{{'
            f'namespace="{NAMESPACE}", '
            f'service="{service}"'
            f'}}[1m])) by (le))'
        )
    else:
        rps = (
            f'sum(rate(http_server_requests_seconds_count{{'
            f'namespace="{NAMESPACE}", '
            f'service="{service}", '
            f'uri!~"/actuator.*"'
            f'}}[1m]))'
        )
        latency = (
            f'histogram_quantile(0.95, sum(rate('
            f'http_server_requests_seconds_bucket{{'
            f'namespace="{NAMESPACE}", '
            f'service="{service}", '
            f'uri!~"/actuator.*"'
            f'}}[1m])) by (le))'
        )

    return {"cpu": cpu, "memory": memory, "replicas": replicas, "rps": rps, "latency": latency}


def collect_once(service: str, queries: dict, prev_rps) -> dict | None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cpu      = query_prometheus(queries["cpu"])
    memory   = query_prometheus(queries["memory"])
    replicas = query_prometheus(queries["replicas"])
    rps      = query_prometheus(queries["rps"])
    latency  = query_prometheus(queries["latency"])

    if None in (cpu, memory, replicas):
        print(f"  [SKIP] {service}: thieu cpu/memory/replicas")
        return None
    if rps is None and latency is None:
        print(f"  [SKIP] {service}: rps va latency deu None")
        return None

    rps     = rps     if rps     is not None else 0.0
    latency = latency if latency is not None else 0.0
    delta_rps = (rps - prev_rps) if prev_rps is not None else 0.0

    return {
        "timestamp": timestamp,
        "cpu":       round(cpu,      6),
        "memory":    int(memory),
        "latency":   round(latency,  6),
        "rps":       round(rps,      6),
        "replicas":  int(replicas),
        "delta_rps": round(delta_rps, 6),
        "_rps_raw":  rps,
    }


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    csv_files, csv_writers = {}, {}
    fieldnames = ["timestamp", "cpu", "memory", "latency", "rps", "replicas", "delta_rps"]

    for svc in SERVICES:
        path = os.path.join(OUTPUT_DIR, f"{svc}_metrics.csv")
        f = open(path, "w", newline="")
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        csv_files[svc] = f
        csv_writers[svc] = writer
        print(f"[INFO] Output: {path}")

    prev_rps = {svc: None for svc in SERVICES}
    queries  = {svc: build_queries(svc) for svc in SERVICES}

    def handle_exit(sig, frame):
        print("\n[INFO] Dang dung, dong file...")
        for f in csv_files.values():
            f.close()
        print("[INFO] Hoan tat. File luu tai:", OUTPUT_DIR)
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_exit)

    print(f"\n[INFO] Thu metrics: {', '.join(SERVICES)}")
    print(f"[INFO] Output: {OUTPUT_DIR}")
    print(f"[INFO] Interval: {INTERVAL}s | Ctrl+C de dung.\n")

    row_count = {svc: 0 for svc in SERVICES}

    while True:
        tick_start = time.time()
        for svc in SERVICES:
            result = collect_once(svc, queries[svc], prev_rps[svc])
            if result:
                prev_rps[svc] = result.pop("_rps_raw")
                csv_writers[svc].writerow(result)
                csv_files[svc].flush()
                row_count[svc] += 1

        if row_count[SERVICES[0]] % 10 == 0 and row_count[SERVICES[0]] > 0:
            now = datetime.now().strftime("%H:%M:%S")
            counts = " | ".join(f"{s}: {row_count[s]}" for s in SERVICES)
            print(f"[{now}] rows -> {counts}")

        elapsed = time.time() - tick_start
        time.sleep(max(0, INTERVAL - elapsed))


if __name__ == "__main__":
    main()