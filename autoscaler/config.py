"""Configuration for RL Autoscaler."""

import os

# Kubernetes Configuration
NAMESPACE = "app"

# Dynamic Target Configuration (from environment variables)
TARGET_DEPLOYMENT = os.getenv("TARGET_DEPLOYMENT", "apigateway")
TARGET_SERVICE = os.getenv("TARGET_SERVICE", TARGET_DEPLOYMENT)

DEPLOYMENT_NAME = TARGET_DEPLOYMENT

# Scaling Constraints
MIN_REPLICAS = 1
MAX_REPLICAS = 3

# Cooldown period (seconds)
COOLDOWN_SECONDS = 60

# RL Model Configuration
ALGO = os.getenv("ALGO", "ppo")  # ppo or a2c
MODEL_PATH = f"models/{ALGO}_k8s_autoscaler.zip"

# Prometheus Configuration
PROM_URL = os.getenv("PROM_URL", "http://prometheus:9090")
PROM_QUERY_TIMEOUT = 10  # seconds

# Metric Query Templates (built dynamically for target service)
# Note: Queries are filtered by TARGET_DEPLOYMENT pod selector
METRIC_QUERIES = {
    "rps": f'sum(rate(http_server_requests_seconds_count{{namespace="app", service="{TARGET_SERVICE}"}}[1m]))',
    "cpu": f'sum(rate(container_cpu_usage_seconds_total{{namespace="app", pod=~"{TARGET_DEPLOYMENT}.*"}}[1m]))',
    "memory": f'sum(container_memory_working_set_bytes{{namespace="app", pod=~"{TARGET_DEPLOYMENT}.*", container!="", image!=""}}) / sum(kube_pod_container_resource_requests{{namespace="app", pod=~"{TARGET_DEPLOYMENT}.*", resource="memory", unit="byte"}})',
    "latency": f'1000 * histogram_quantile(0.95, sum by (le) (rate(http_server_requests_seconds_bucket{{namespace="app", service="{TARGET_SERVICE}"}}[1m])))',
    "replicas": f'kube_deployment_status_replicas{{namespace="app", deployment="{TARGET_DEPLOYMENT}"}}',
}

# Normalization Constants (from training - DO NOT MODIFY)
NORMALIZATION = {
    "rps": 99.7,
    "cpu": 110.0,
    "memory": 81.1,
    "latency": 885.0,
    "replicas": 3.0,  # Runtime max (training was 10)
}

# Logging level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
