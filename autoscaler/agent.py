"""DRL Autoscaling Agent - Main Loop.

Agent runs an infinite loop that:
1. Queries Prometheus for 18 metrics (6 per service)
2. Normalizes state using MinMaxScaler
3. Runs model.predict() to get action
4. Converts action index to replica delta
5. Patches Kubernetes deployment scale
6. Logs results
"""

import logging
import os
import sys
import time
from typing import Optional, Dict, List
import numpy as np
import joblib

# Kubernetes
from kubernetes import client, config as k8s_config

# HTTP
import requests

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Configuration from Environment
# ============================================================================

PROMETHEUS_URL = os.getenv(
    "PROMETHEUS_URL", 
    "http://prometheus-server.monitoring.svc.cluster.local"
)
TARGET_NAMESPACE = os.getenv("TARGET_NAMESPACE", "app")
SCALE_INTERVAL = int(os.getenv("SCALE_INTERVAL", "15"))  # seconds
MODEL_PATH = os.getenv("MODEL_PATH", "/app/models/ppo_model_best.zip")
SCALER_PATH = os.getenv("SCALER_PATH", "/app/models/scaler.pkl")
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Services to scale (order matters for model input!)
SERVICES = ["cartservice", "productcatalogservice", "apigateway"]
MIN_REPLICAS = 1
MAX_REPLICAS = 10

# Prom query timeout
PROM_TIMEOUT = 10


# ============================================================================
# PromQL Queries (Prometheus)
# ============================================================================

def get_prom_queries() -> Dict[str, Dict[str, str]]:
    """Build PromQL queries for all services.
    
    Returns:
        Dict[service] -> Dict[metric] -> PromQL query
    """
    queries = {
        "cartservice": {
            "cpu": (
                'sum(rate(container_cpu_usage_seconds_total{'
                'namespace="app", pod=~"cartservice.*", container!=""}[1m]))'
            ),
            "memory": (
                'sum(container_memory_working_set_bytes{'
                'namespace="app", pod=~"cartservice.*", container!=""})'
            ),
            "latency": (
                'histogram_quantile(0.95, sum(rate('
                'http_server_requests_seconds_bucket{'
                'namespace="app", service="cartservice", uri!~"/actuator.*"'
                '}[1m])) by (le))'
            ),
            "rps": (
                'sum(rate(http_server_requests_seconds_count{'
                'namespace="app", service="cartservice", uri!~"/actuator.*"'
                '}[1m]))'
            ),
            "replicas": (
                'kube_deployment_status_replicas{'
                'namespace="app", deployment="cartservice"}'
            ),
        },
        "productcatalogservice": {
            "cpu": (
                'sum(rate(container_cpu_usage_seconds_total{'
                'namespace="app", pod=~"productcatalogservice.*", container!=""}[1m]))'
            ),
            "memory": (
                'sum(container_memory_working_set_bytes{'
                'namespace="app", pod=~"productcatalogservice.*", container!=""})'
            ),
            "latency": (
                'histogram_quantile(0.95, sum(rate('
                'http_server_requests_seconds_bucket{'
                'namespace="app", service="productcatalogservice", uri!~"/actuator.*"'
                '}[1m])) by (le))'
            ),
            "rps": (
                'sum(rate(http_server_requests_seconds_count{'
                'namespace="app", service="productcatalogservice", uri!~"/actuator.*"'
                '}[1m]))'
            ),
            "replicas": (
                'kube_deployment_status_replicas{'
                'namespace="app", deployment="productcatalogservice"}'
            ),
        },
        "apigateway": {
            "cpu": (
                'sum(rate(container_cpu_usage_seconds_total{'
                'namespace="app", pod=~"apigateway.*", container!=""}[1m]))'
            ),
            "memory": (
                'sum(container_memory_working_set_bytes{'
                'namespace="app", pod=~"apigateway.*", container!=""})'
            ),
            "latency": (
                'histogram_quantile(0.95, sum(rate('
                'http_server_requests_seconds_bucket{'
                'namespace="app", service="apigateway"'
                '}[1m])) by (le))'
            ),
            "rps": (
                'sum(rate(http_server_requests_seconds_count{'
                'namespace="app", service="apigateway"'
                '}[1m]))'
            ),
            "replicas": (
                'kube_deployment_status_replicas{'
                'namespace="app", deployment="apigateway"}'
            ),
        },
    }
    return queries


# ============================================================================
# Prometheus Client
# ============================================================================

class PrometheusClient:
    """Simple Prometheus query client."""
    
    def __init__(self, url: str):
        self.url = url
        self.query_endpoint = f"{url}/api/v1/query"
    
    def query(self, promql: str) -> Optional[float]:
        """Execute PromQL query and return single scalar value.
        
        Args:
            promql: PromQL query string
            
        Returns:
            Float value or None if query fails/returns no data
        """
        try:
            resp = requests.get(
                self.query_endpoint,
                params={"query": promql},
                timeout=PROM_TIMEOUT,
            )
            resp.raise_for_status()
            
            data = resp.json()
            if data.get("status") != "success":
                logger.warning(f"Prometheus error: {data.get('error')}")
                return None
            
            results = data.get("data", {}).get("result", [])
            if not results:
                logger.debug(f"No data for query: {promql[:80]}...")
                return None
            
            # Return first value
            value_str = results[0].get("value", [None, None])[1]
            if value_str is None:
                return None
                
            return float(value_str)
        except Exception as e:
            logger.error(f"Prometheus query failed: {e}")
            return None


# ============================================================================
# Kubernetes Client
# ============================================================================

class KubernetesClient:
    """Kubernetes API client for scaling."""
    
    def __init__(self, namespace: str):
        self.namespace = namespace
        
        try:
            k8s_config.load_incluster_config()
            logger.info("Loaded in-cluster Kubernetes config")
        except Exception as e:
            logger.warning(f"In-cluster config failed: {e}, trying local config...")
            try:
                k8s_config.load_kube_config()
                logger.info("Loaded local Kubernetes config")
            except Exception as e2:
                logger.error(f"Failed to load Kubernetes config: {e2}")
                raise
        
        self.apps_api = client.AppsV1Api()
    
    def get_replicas(self, deployment: str) -> Optional[int]:
        """Get current replicas for deployment.
        
        Args:
            deployment: Deployment name
            
        Returns:
            Current replica count or None if failed
        """
        try:
            dep = self.apps_api.read_namespaced_deployment(deployment, self.namespace)
            replicas = dep.spec.replicas or 1
            return replicas
        except Exception as e:
            logger.error(f"Failed to get replicas for {deployment}: {e}")
            return None
    
    def scale_deployment(self, deployment: str, replicas: int) -> bool:
        """Scale deployment to target replicas.
        
        Args:
            deployment: Deployment name
            replicas: Target replica count
            
        Returns:
            True if successful, False otherwise
        """
        try:
            body = {"spec": {"replicas": replicas}}
            self.apps_api.patch_namespaced_deployment_scale(
                deployment, self.namespace, body
            )
            logger.info(f"Scaled {deployment} to {replicas} replicas")
            return True
        except Exception as e:
            logger.error(f"Failed to scale {deployment}: {e}")
            return False


# ============================================================================
# DRL Agent
# ============================================================================

class DRLAutoscalerAgent:
    """Deep Reinforcement Learning Autoscaler Agent."""
    
    def __init__(self):
        logger.info("Initializing DRL Autoscaler Agent...")
        logger.info(f"  Prometheus URL: {PROMETHEUS_URL}")
        logger.info(f"  Namespace: {TARGET_NAMESPACE}")
        logger.info(f"  Scale interval: {SCALE_INTERVAL}s")
        logger.info(f"  Model path: {MODEL_PATH}")
        logger.info(f"  Scaler path: {SCALER_PATH}")
        logger.info(f"  DRY_RUN: {DRY_RUN}")
        
        # Load model
        try:
            from stable_baselines3 import PPO
            self.model = PPO.load(MODEL_PATH)
            logger.info(f"Loaded PPO model from {MODEL_PATH}")
        except Exception as e:
            logger.error(f"Failed to load model: {e}")
            raise
        
        # Load scaler
        try:
            self.scaler = joblib.load(SCALER_PATH)
            logger.info(f"Loaded MinMaxScaler from {SCALER_PATH}")
        except Exception as e:
            logger.error(f"Failed to load scaler: {e}")
            raise
        
        # Initialize clients
        self.prom_client = PrometheusClient(PROMETHEUS_URL)
        self.k8s_client = KubernetesClient(TARGET_NAMESPACE)
        
        # PromQL queries
        self.queries = get_prom_queries()
        
        # State tracking
        self.prev_rps = {service: 0.0 for service in SERVICES}
        self.iteration = 0
        
        logger.info("DRL Autoscaler Agent initialized successfully")
    
    def collect_metrics(self) -> Optional[Dict[str, Dict[str, float]]]:
        """Collect all metrics from Prometheus.
        
        Returns:
            Dict[service] -> Dict[metric] -> value, or None if critical failure
        """
        metrics = {}
        
        for service in SERVICES:
            metrics[service] = {}
            service_queries = self.queries[service]
            
            for metric, query in service_queries.items():
                value = self.prom_client.query(query)
                
                # Handle None values
                if value is None:
                    if metric == "replicas":
                        # Skip if replicas is None
                        logger.warning(
                            f"[{service}] {metric} returned None, "
                            "skipping this step"
                        )
                        return None
                    else:
                        # Use 0.0 for other metrics
                        value = 0.0
                        logger.debug(f"[{service}] {metric} = None, using 0.0")
                
                metrics[service][metric] = value
                logger.debug(f"[{service}] {metric} = {value}")
        
        return metrics
    
    def build_state_vector(self, metrics: Dict[str, Dict]) -> np.ndarray:
        """Build 18-feature state vector in correct order.
        
        Order (MUST NOT CHANGE):
        [0]   cpu_cart
        [1]   memory_cart
        [2]   latency_cart
        [3]   rps_cart
        [4]   replicas_cart
        [5]   delta_rps_cart
        
        [6]   cpu_product
        [7]   memory_product
        [8]   latency_product
        [9]   rps_product
        [10]  replicas_product
        [11]  delta_rps_product
        
        [12]  cpu_gateway
        [13]  memory_gateway
        [14]  latency_gateway
        [15]  rps_gateway
        [16]  replicas_gateway
        [17]  delta_rps_gateway
        """
        state = []
        
        for service in SERVICES:  # ["cartservice", "productcatalogservice", "apigateway"]
            service_metrics = metrics[service]
            
            # cpu, memory, latency, rps, replicas
            cpu = service_metrics.get("cpu", 0.0)
            memory = service_metrics.get("memory", 0.0)
            latency = service_metrics.get("latency", 0.0)  # already in seconds
            rps = service_metrics.get("rps", 0.0)
            replicas = service_metrics.get("replicas", 0.0)
            
            # Calculate delta_rps
            delta_rps = rps - self.prev_rps[service]
            self.prev_rps[service] = rps
            
            # Append in order: cpu, memory, latency, rps, replicas, delta_rps
            state.extend([
                cpu,
                memory,
                latency,
                rps,
                replicas,
                delta_rps,
            ])
        
        state_array = np.array(state, dtype=np.float32).reshape(1, -1)
        
        logger.debug(f"Raw state vector (shape {state_array.shape}): {state_array}")
        
        # Normalize + clip to [0,1] to match training distribution
        normalized_state = np.clip(
            self.scaler.transform(state_array), 0.0, 1.0
        )
        
        logger.debug(f"Normalized state: {normalized_state}")
        
        return normalized_state
    
    def action_to_delta_replicas(self, action_indices: np.ndarray) -> Dict[str, int]:
        """Convert action indices to replica deltas.
        
        Action space: indices 0-6 map to delta -3 to +3
        
        Args:
            action_indices: Array of 3 action indices [0..6]
            
        Returns:
            Dict[service] -> delta_replicas
        """
        delta_map = {
            0: -3,
            1: -2,
            2: -1,
            3: 0,
            4: +1,
            5: +2,
            6: +3,
        }
        
        deltas = {}
        for service, action_idx in zip(SERVICES, action_indices):
            action_idx = int(action_idx)  # Ensure int
            delta = delta_map.get(action_idx, 0)
            deltas[service] = delta
            logger.info(f"[{service}] action_index={action_idx} → delta={delta:+d}")
        
        return deltas
    
    def apply_scaling(self, deltas: Dict[str, int], current_replicas: Dict[str, int]) -> None:
        """Apply scaling actions to deployments.
        
        Args:
            deltas: Dict[service] -> delta_replicas
            current_replicas: Dict[service] -> current_replicas
        """
        for service, delta in deltas.items():
            if delta == 0:
                logger.info(f"[{service}] No scaling action (delta=0)")
                continue
            
            current = current_replicas[service]
            new_replicas = max(MIN_REPLICAS, min(MAX_REPLICAS, current + delta))
            
            logger.info(
                f"[{service}] Scaling: {current} → {new_replicas} "
                f"(delta={delta:+d})"
            )
            
            if DRY_RUN:
                logger.info(f"[{service}] DRY_RUN: skipping actual scale")
            else:
                self.k8s_client.scale_deployment(service, new_replicas)
    
    def run_once(self) -> bool:
        """Run one autoscaling iteration.
        
        Returns:
            True if iteration completed, False if skipped due to error
        """
        self.iteration += 1
        logger.info(f"\n{'='*70}")
        logger.info(f"Iteration {self.iteration}")
        logger.info(f"{'='*70}")
        
        # Collect metrics
        logger.info("Collecting metrics from Prometheus...")
        metrics = self.collect_metrics()
        if metrics is None:
            logger.warning("Skipping iteration due to missing critical metrics")
            return False
        
        # Get current replicas
        current_replicas = {}
        for service in SERVICES:
            replicas = self.k8s_client.get_replicas(service)
            if replicas is None:
                replicas = 1
            current_replicas[service] = replicas
            logger.info(f"[{service}] Current replicas: {replicas}")
        
        # Check idle state
        total_rps = sum(metrics[svc].get('rps', 0) for svc in SERVICES)
        total_cpu = sum(metrics[svc].get('cpu', 0) for svc in SERVICES)
        
        # Thresholds for idle detection
        IDLE_RPS_THRESHOLD = 1.0   # req/s
        IDLE_CPU_THRESHOLD = 0.05  # cores
        
        # If system is idle → force scale down to minimum
        if total_rps < IDLE_RPS_THRESHOLD and total_cpu < IDLE_CPU_THRESHOLD:
            logger.info(
                f"System idle (rps={total_rps:.2f}, cpu={total_cpu:.3f}), "
                "forcing scale down to minimum"
            )
            for svc in SERVICES:
                current = current_replicas.get(svc, 1)
                if current > 1:
                    self.k8s_client.scale_deployment(svc, 1)
                    logger.info(f"[{svc}] Idle scale down: {current} → 1")
            return True
        
        # Normal mode: predict action from model
        logger.info("Building state vector...")
        state = self.build_state_vector(metrics)
        
        # Predict action
        logger.info("Predicting action...")
        action, _ = self.model.predict(state, deterministic=True)
        action = action.flatten()  # (1,3) → (3,)
        logger.info(f"Raw action output: {action}")
        
        # Convert to deltas
        deltas = self.action_to_delta_replicas(action)
        
        # Apply scaling
        logger.info("Applying scaling decisions...")
        self.apply_scaling(deltas, current_replicas)
        
        return True
    
    def run(self) -> None:
        """Run infinite autoscaling loop."""
        logger.info(f"Starting autoscaling loop (interval={SCALE_INTERVAL}s)...")
        
        try:
            while True:
                try:
                    self.run_once()
                except Exception as e:
                    logger.error(f"Error in autoscaling loop: {e}", exc_info=True)
                
                logger.info(f"Sleeping {SCALE_INTERVAL}s until next iteration...")
                time.sleep(SCALE_INTERVAL)
        except KeyboardInterrupt:
            logger.info("Autoscaler stopped by user")
        except Exception as e:
            logger.error(f"Fatal error in autoscaler: {e}", exc_info=True)
            sys.exit(1)


# ============================================================================
# Main
# ============================================================================

def main():
    """Main entry point."""
    agent = DRLAutoscalerAgent()
    agent.run()


if __name__ == "__main__":
    main()
