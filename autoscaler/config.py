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
MODEL_PATH = f"models/{ALGO}_autoscaler.zip"  # Trained model file

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
        "rps": f'sum(rate(http_server_requests_seconds_count{{namespace="app", service=~"{service_name}.*", uri!~".*actuator.*"}}[1m]))',
        "cpu": f'avg(rate(container_cpu_usage_seconds_total{{namespace="app", pod=~"{deployment_name}-.*"}}[1m])) * 100',
        "memory": f'avg(container_memory_working_set_bytes{{namespace="app", pod=~"{deployment_name}-.*"}}) / avg(kube_pod_container_resource_limits{{namespace="app", resource="memory", pod=~"{deployment_name}-.*"}}) * 100',
        "latency": f'histogram_quantile(0.95, sum(rate(http_server_requests_seconds_bucket{{namespace="app", service=~"{service_name}.*"}}[1m])) by (le)) * 1000',
        "replicas": f'kube_deployment_status_replicas_available{{namespace="app", deployment="{deployment_name}"}}',
    }

# Normalization Constants (z-score normalization from training)
# These are from the trained model's VecNormalize statistics
NORMALIZATION_MEAN = {
    "rps": 74.11146559075515,
    "cpu": 2.8096141731420605,
    "memory": 24.96668951185495,
    "latency_p95": 7.399000488145049,
    "replicas": 2.675483163976888,
    "delta_rps": -0.08351009165172346,
}

NORMALIZATION_SCALE = {
    "rps": 40.80411621911202,
    "cpu": 1.6160535038892168,
    "memory": 2.3825732209776818,
    "latency_p95": 14.707872050780225,
    "replicas": 1.452357785377225,
    "delta_rps": 10.003825043583488,
}

# Legacy: kept for backward compatibility (deprecated, use NORMALIZATION_MEAN/SCALE)
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
