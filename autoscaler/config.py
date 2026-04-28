"""Configuration for RL Autoscaler."""

import os

# Kubernetes Configuration
NAMESPACE = "app"

# Multi-service Configuration
TARGET_SERVICES = ["apigateway", "productcatalogservice", "cartservice"]

# Scaling Constraints
MIN_REPLICAS = 1
MAX_REPLICAS = 8  # Maximum replicas per service

# Directional Cooldown (RL-aware)
COOLDOWN_SCALE_UP = 15    # Short cooldown for scale-up (responsive to load spike)
COOLDOWN_SCALE_DOWN = 60  # Long cooldown for scale-down (avoid flapping)

# Emergency Detection Thresholds
LATENCY_CRITICAL = 500    # ms - bypass cooldown when latency exceeds this
RPS_SPIKE_PERCENT = 50    # % - RPS increase threshold

# Adaptive Scaling
ADAPTIVE_STEP = True      # Enable multi-step scaling based on normalized metrics
COOLDOWN_SECONDS = 60     # Legacy: kept for compatibility

# RL Model Configuration
ALGO = os.getenv("ALGO", "ppo")  # ppo or a2c
MODEL_PATH = f"models/{ALGO}_k8s_autoscaler.zip"

# Prometheus Configuration
# Using FQDN to access monitoring-kube-prometheus-prometheus from app namespace
PROM_URL = os.getenv("PROM_URL", "http://monitoring-kube-prometheus-prometheus.monitoring:9090")
PROM_QUERY_TIMEOUT = 10  # seconds

# Helper function to build metric queries for a specific service
def build_metric_queries(service_name: str, deployment_name: str) -> dict:
    """Build metric queries for a specific service.
    
    Args:
        service_name: Service name for HTTP metrics (e.g., "apigateway")
        deployment_name: Deployment name for pod selectors (e.g., "apigateway")
    
    Returns:
        Dict with Prometheus queries for this service
    """
    return {
        "rps": f'sum(rate(http_server_requests_seconds_count{{namespace="app", service="{service_name}"}}[1m]))',
        "cpu": f'sum(rate(container_cpu_usage_seconds_total{{namespace="app", pod=~"{deployment_name}.*"}}[1m]))',
        "memory": f'sum(container_memory_working_set_bytes{{namespace="app", pod=~"{deployment_name}.*", container!="", image!=""}}) / sum(kube_pod_container_resource_requests{{namespace="app", pod=~"{deployment_name}.*", resource="memory", unit="byte"}})',
        "latency": f'1000 * histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{{namespace="app", service="{service_name}"}}[1m])))',
        "replicas": f'kube_deployment_status_replicas{{namespace="app", deployment="{deployment_name}"}}',
    }

# Normalization Constants (updated for MAX_REPLICAS=8)
NORMALIZATION = {
    "rps": 99.7,
    "cpu": 110.0,
    "memory": 81.1,
    "latency": 885.0,
    "replicas": 8.0,  # Updated: Runtime max = 8
}

# Logging level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
