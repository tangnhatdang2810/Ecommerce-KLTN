"""Configuration for RL Autoscaler."""

import os

# Kubernetes Configuration
NAMESPACE = "app"

# Multi-service Configuration
TARGET_SERVICES = ["apigateway", "productcatalogservice", "cartservice"]

# Scaling Constraints
MIN_REPLICAS = 1
MAX_REPLICAS = 6  # Maximum replicas per service (trained with 6)

# Directional Cooldown (RL-aware)
COOLDOWN_SCALE_UP = 15    # Short cooldown for scale-up (responsive to load spike)
COOLDOWN_SCALE_DOWN = 60  # Long cooldown for scale-down (avoid flapping)

# Emergency Detection Thresholds
LATENCY_CRITICAL = 500    # ms - bypass cooldown when latency exceeds this
RPS_SPIKE_PERCENT = 50    # % - RPS increase threshold

# Reward Function Parameters (from trained model)
SLA_LATENCY = 100.0       # ms - SLA target threshold
CPU_TARGET = 2.6          # % - Target CPU utilization
MEM_TARGET = 25.0         # % - Target memory utilization

# Action Mapping (RL model output)
ACTION_MAP = {0: -1, 1: 0, 2: 1}  # 0=scale_down(-1), 1=stay(0), 2=scale_up(+1)
ACTION_NAMES = {0: "scale_down", 1: "stay", 2: "scale_up"}

# Adaptive Scaling
ADAPTIVE_STEP = True      # Enable multi-step scaling based on normalized metrics
COOLDOWN_SECONDS = 60     # Legacy: kept for compatibility

# RL Model Configuration
ALGO = os.getenv("ALGO", "ppo")  # ppo or a2c (ppo is default, trained model)
MODEL_PATH = f"models/{ALGO}_autoscaler_final.zip"  # Trained model file

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

# Normalization Constants (updated for MAX_REPLICAS=6, trained on synthetic dataset)
NORMALIZATION = {
    "rps": 99.7,         # 1-minute RPS rate
    "cpu": 110.0,        # CPU usage in percent
    "memory": 81.1,      # Memory usage in percent
    "latency": 885.0,    # P95 latency in milliseconds
    "replicas": 6.0,     # Runtime max = 6 (trained max)
    "delta_rps": 50.0,   # RPS change rate (approximate from data)
}

# Logging level
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
