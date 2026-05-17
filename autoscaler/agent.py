"""
DRL Autoscaling Agent - Sequential Multi-Service
1 pod duy nhất, loop qua 3 services tuần tự.
Mỗi service dùng cùng 1 model nhưng collect 6 features riêng.

Kiến trúc:
  - 1 PPO model (train từ productcatalog data)
  - 1 scaler_single.pkl (6 features)
  - Mỗi iteration: loop qua cart → product → gateway
  - Mỗi service: collect 6 metrics → predict action → scale

Env vars:
  PROMETHEUS_URL:   URL Prometheus in-cluster
  TARGET_NAMESPACE: namespace của services
  SCALE_INTERVAL:   interval giữa các lần scale (giây)
  MODEL_PATH:       path đến PPO model
  SCALER_PATH:      path đến scaler_single.pkl
  DRY_RUN:          true/false
"""

import logging
import os
import sys
import time
from typing import Optional, Dict
import numpy as np
import joblib
from kubernetes import client, config as k8s_config
import requests

# ============================================================================
# Logging
# ============================================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================
PROMETHEUS_URL   = os.getenv("PROMETHEUS_URL", "http://monitoring-kube-prometheus-prometheus.monitoring.svc.cluster.local:9090")
TARGET_NAMESPACE = os.getenv("TARGET_NAMESPACE", "app")
SCALE_INTERVAL   = int(os.getenv("SCALE_INTERVAL", "15"))
MODEL_PATH       = os.getenv("MODEL_PATH", "/app/models/a2c_single_best.zip")
SCALER_PATH      = os.getenv("SCALER_PATH", "/app/models/scaler_single.pkl")
DRY_RUN          = os.getenv("DRY_RUN", "false").lower() == "true"

# 3 services cần scale - thứ tự không ảnh hưởng vì mỗi service độc lập
SERVICES = ["cartservice", "productcatalogservice", "apigateway"]

MIN_REPLICAS = 1
MAX_REPLICAS = 10
PROM_TIMEOUT = 10

# Idle detection
IDLE_RPS_THRESHOLD = 1.0
IDLE_CPU_THRESHOLD = 0.05
IDLE_COOLDOWN      = 60


# ============================================================================
# PromQL Queries
# ============================================================================
def build_queries(service: str) -> Dict[str, str]:
    """Build PromQL queries cho 1 service (6 metrics)."""
    is_gateway = (service == "apigateway")
    uri_filter = '' if is_gateway else ', uri!~"/actuator.*"'
    ns = TARGET_NAMESPACE
    return {
        "cpu":      f'sum(rate(container_cpu_usage_seconds_total{{namespace="{ns}",pod=~"{service}.*",container!=""}}[1m]))',
        "memory":   f'sum(container_memory_working_set_bytes{{namespace="{ns}",pod=~"{service}.*",container!=""}})',
        "latency":  f'histogram_quantile(0.95,sum(rate(http_server_requests_seconds_bucket{{namespace="{ns}",service="{service}"{uri_filter}}}[1m]))by(le))',
        "rps":      f'sum(rate(http_server_requests_seconds_count{{namespace="{ns}",service="{service}"{uri_filter}}}[1m]))',
        "replicas": f'kube_deployment_status_replicas{{namespace="{ns}",deployment="{service}"}}',
    }


# ============================================================================
# Prometheus Client
# ============================================================================
class PrometheusClient:
    def __init__(self, url: str):
        self.endpoint = f"{url}/api/v1/query"

    def query(self, promql: str) -> Optional[float]:
        try:
            resp = requests.get(
                self.endpoint,
                params={"query": promql},
                timeout=PROM_TIMEOUT,
            )
            resp.raise_for_status()
            results = resp.json().get("data", {}).get("result", [])
            return float(results[0]["value"][1]) if results else None
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return None


# ============================================================================
# Kubernetes Client
# ============================================================================
class KubernetesClient:
    def __init__(self, namespace: str):
        self.namespace = namespace
        try:
            k8s_config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except Exception:
            k8s_config.load_kube_config()
            logger.info("Loaded local Kubernetes config")
        self.apps_api = client.AppsV1Api()

    def get_replicas(self, deployment: str) -> Optional[int]:
        try:
            dep = self.apps_api.read_namespaced_deployment(
                name=deployment, namespace=self.namespace
            )
            return dep.spec.replicas or 1
        except Exception as e:
            logger.error(f"get_replicas({deployment}) failed: {e}")
            return None

    def scale_deployment(self, deployment: str, replicas: int) -> bool:
        try:
            self.apps_api.patch_namespaced_deployment_scale(
                name=deployment,
                namespace=self.namespace,
                body={"spec": {"replicas": replicas}},
            )
            logger.info(f"Scaled {deployment} to {replicas} replicas")
            return True
        except Exception as e:
            logger.error(f"scale_deployment({deployment}) failed: {e}")
            return False


# ============================================================================
# DRL Agent - Sequential Multi-Service
# ============================================================================
class DRLAutoscalerAgent:
    def __init__(self):
        logger.info("Initializing DRL Autoscaler Agent (Sequential Multi-Service)...")
        logger.info(f"  Services:        {SERVICES}")
        logger.info(f"  Prometheus URL:  {PROMETHEUS_URL}")
        logger.info(f"  Namespace:       {TARGET_NAMESPACE}")
        logger.info(f"  Scale interval:  {SCALE_INTERVAL}s")
        logger.info(f"  Model path:      {MODEL_PATH}")
        logger.info(f"  Scaler path:     {SCALER_PATH}")
        logger.info(f"  DRY_RUN:         {DRY_RUN}")

        # Load A2C model (dùng chung cho cả 3 services)
        from stable_baselines3 import A2C
        self.model = A2C.load(MODEL_PATH)
        logger.info(f"Loaded A2C model from {MODEL_PATH}")

        # Load scaler 6 features (dùng chung cho cả 3 services)
        self.scaler = joblib.load(SCALER_PATH)
        logger.info(f"Loaded scaler from {SCALER_PATH}")

        # Clients
        self.prom = PrometheusClient(PROMETHEUS_URL)
        self.k8s  = KubernetesClient(TARGET_NAMESPACE)

        # Build queries cho từng service
        self.queries = {svc: build_queries(svc) for svc in SERVICES}

        # Per-service state tracking
        self.prev_rps = {svc: 0.0 for svc in SERVICES}
        self.last_idle_scaledown_time = {svc: 0 for svc in SERVICES}

        self.iteration = 0
        logger.info("DRL Autoscaler Agent initialized successfully")

    def collect_metrics(self, service: str) -> Optional[Dict[str, float]]:
        """Thu thập 5 metrics từ Prometheus cho 1 service."""
        q = self.queries[service]
        cpu_total    = self.prom.query(q["cpu"])
        memory_total = self.prom.query(q["memory"])
        latency      = self.prom.query(q["latency"])
        rps          = self.prom.query(q["rps"])
        replicas     = self.prom.query(q["replicas"])

        if replicas is None or replicas == 0:
            logger.warning(f"[{service}] replicas returned None, skipping")
            return None

        reps = int(replicas)

        # Per-pod conversion - khớp với training data
        cpu_per_pod    = (cpu_total    or 0.0) / max(reps, 1)
        memory_per_pod = (memory_total or 0.0) / max(reps, 1)

        return {
            "cpu":      cpu_per_pod,
            "memory":   memory_per_pod,
            "latency":  latency  or 0.0,
            "rps":      rps      or 0.0,
            "replicas": reps,
        }

    def build_state_vector(self, service: str, metrics: Dict[str, float]) -> np.ndarray:
        """
        Build 6-feature state cho 1 service:
        [cpu, memory, latency, rps, replicas, delta_rps]
        """
        rps = metrics["rps"]
        delta_rps = rps - self.prev_rps[service]
        self.prev_rps[service] = rps

        state = np.array([[
            metrics["cpu"],
            metrics["memory"],
            metrics["latency"],
            rps,
            metrics["replicas"],
            delta_rps,
        ]], dtype=np.float32)

        # Input validation
        if np.any(np.isnan(state)) or np.any(state < 0):
            logger.warning(f"[{service}] Abnormal state: cpu={metrics['cpu']:.4f}, "
                          f"mem={metrics['memory']:.0f}, lat={metrics['latency']:.4f}, "
                          f"rps={rps:.2f}, replicas={metrics['replicas']}, delta_rps={delta_rps:.4f}")

        return np.clip(self.scaler.transform(state), 0.0, 1.0)

    def scale_service(self, service: str) -> None:
        """Scale 1 service: collect → predict → scale."""
        # 1. Thu metrics
        metrics = self.collect_metrics(service)
        if metrics is None:
            return

        current_replicas = metrics["replicas"]
        rps = metrics["rps"]
        cpu = metrics["cpu"]

        logger.info(
            f"[{service}] replicas={current_replicas} | "
            f"rps={rps:.2f} | cpu={cpu:.4f} | "
            f"lat={metrics['latency']*1000:.1f}ms"
        )

        # 4. Build state và predict
        state      = self.build_state_vector(service, metrics)
        action, _  = self.model.predict(state, deterministic=True)
        action_idx = int(action[0]) if isinstance(action, np.ndarray) else int(action)
        delta      = action_idx - 3
        logger.info(f"[{service}] action={action_idx} → delta={delta:+d}")

        # 5. Scale
        new_replicas = int(np.clip(current_replicas + delta, MIN_REPLICAS, MAX_REPLICAS))
        if new_replicas != current_replicas:
            direction = "↑" if delta > 0 else "↓"
            logger.info(f"[{service}] Scaling: {current_replicas} {direction} {new_replicas}")
            if not DRY_RUN:
                self.k8s.scale_deployment(service, new_replicas)
        else:
            logger.info(f"[{service}] No scaling action (delta=0)")

    def run_once(self) -> None:
        """1 iteration: loop qua cả 3 services tuần tự."""
        self.iteration += 1
        logger.info(f"\n{'='*60}")
        logger.info(f"Iteration {self.iteration}")
        logger.info(f"{'='*60}")

        for service in SERVICES:
            try:
                self.scale_service(service)
            except Exception as e:
                logger.error(f"[{service}] Error: {e}", exc_info=True)

    def run(self) -> None:
        """Infinite autoscaling loop."""
        logger.info(f"Starting autoscaling loop (interval={SCALE_INTERVAL}s)...")
        try:
            while True:
                tick_start = time.time()
                try:
                    self.run_once()
                except Exception as e:
                    logger.error(f"Error in loop: {e}", exc_info=True)

                # Giữ đúng interval
                elapsed    = time.time() - tick_start
                sleep_time = max(0, SCALE_INTERVAL - elapsed)
                logger.info(f"Sleeping {sleep_time:.1f}s until next iteration...")
                time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Autoscaler stopped by user")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)


# ============================================================================
# Main
# ============================================================================
def main():
    DRLAutoscalerAgent().run()


if __name__ == "__main__":
    main()