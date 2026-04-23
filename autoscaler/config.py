"""Configuration for RL Autoscaler."""

import os

# Kubernetes Configuration
NAMESPACE = "app"

# Multi-service Configuration
TARGET_SERVICES = ["apigateway", "productcatalogservice", "cartservice"]

# Scaling Constraints
MIN_REPLICAS = 1
MAX_REPLICAS = 5

# Cooldown period (seconds) - per service
COOLDOWN_SECONDS = 60

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

# Normalization Constants (from training - DO NOT MODIFY)
NORMALIZATION = {
    "rps": 99.7,
    "cpu": 110.0,
    "memory": 81.1,
    "latency": 885.0,
    "replicas": 5.0,  # Runtime max
}

# Logging level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
