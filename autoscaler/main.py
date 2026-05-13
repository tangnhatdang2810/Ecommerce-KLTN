"""Main entry point for centralized multi-service RL Kubernetes autoscaler."""

import logging
import sys
import time
from typing import Optional, Dict
import numpy as np

from config import (
    NAMESPACE,
    TARGET_SERVICES,
    MODEL_PATH,
    MIN_REPLICAS,
    MAX_REPLICAS,
    LOG_LEVEL,
    build_metric_queries,
)
from prometheus_client import PrometheusClient
from scaler import KubernetesScaler
from model import RLModel
from utils import normalize_metrics, action_to_scaling

# Configure logging
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


class ServiceState:
    """State tracking for a single service."""

    def __init__(self, service_name: str, deployment_name: str):
        """Initialize service state.
        
        Args:
            service_name: Service name (for HTTP metrics)
            deployment_name: Deployment name (for pod selectors)
        """
        self.service_name = service_name
        self.deployment_name = deployment_name
        self.previous_rps = 0.0
        self.iteration = 0
        # Build metric queries specific to this service
        self.metric_queries = build_metric_queries(service_name, deployment_name)


class RLAutoscaler:
    """Centralized multi-service RL-based Kubernetes autoscaler."""

    def __init__(self):
        """Initialize autoscaler components."""
        logger.info("Initializing Centralized Multi-Service RL Autoscaler...")

        # Initialize Prometheus client (shared)
        self.prom_client = PrometheusClient()

        # Initialize Kubernetes scaler (shared)
        self.k8s_scaler = KubernetesScaler(NAMESPACE, None)

        # Load RL model (shared)
        try:
            self.model = RLModel(MODEL_PATH)
            logger.info(f"RL Model loaded: {self.model}")
        except Exception as e:
            logger.error(f"Failed to load RL model: {e}")
            raise

        # Initialize per-service states
        self.service_states: Dict[str, ServiceState] = {}
        for service in TARGET_SERVICES:
            self.service_states[service] = ServiceState(service, service)

        self.global_iteration = 0

        logger.info(
            f"RL Autoscaler initialized successfully for services: {TARGET_SERVICES}"
        )

    def collect_service_metrics(self, service: ServiceState) -> Optional[dict]:
        """Collect metrics from Prometheus for a specific service.

        Args:
            service: Service state object with metric queries

        Returns:
            Dict with metrics, or None if collection failed
        """
        metrics = {}
        
        for metric_name, query in service.metric_queries.items():
            try:
                value = self.prom_client.query_metric(metric_name, query)
                metrics[metric_name] = value
            except Exception as e:
                logger.warning(f"[{service.service_name}] Failed to query {metric_name}: {e}")
                metrics[metric_name] = None

        # Check if we have valid data
        if not all(v is not None for v in metrics.values()):
            logger.warning(
                f"[{service.service_name}] Some metrics are missing: {metrics}"
            )

        return metrics

    def make_scaling_decision(
        self, service: ServiceState, metrics: dict, current_replicas: int
    ) -> tuple[int, str, dict]:
        """Use RL model to make scaling decision for a service.

        Args:
            service: Service state object
            metrics: Collected metrics
            current_replicas: Current replica count

        Returns:
            Tuple of (target_replicas, action_name, normalized_state_dict)
        """
        try:
            # Normalize metrics using service's previous_rps
            state, normalized = normalize_metrics(metrics, service.previous_rps)

            logger.debug(
                f"[{service.service_name}] Normalized state: {normalized}"
            )

            # Get action from RL model
            action, _ = self.model.predict(state, deterministic=True)

            # Convert action to scaling decision
            target_replicas, action_name = action_to_scaling(
                action, current_replicas, MIN_REPLICAS, MAX_REPLICAS
            )

            return target_replicas, action_name, normalized

        except Exception as e:
            logger.error(
                f"[{service.service_name}] Failed to make scaling decision: {e}"
            )
            return current_replicas, "ERROR", {}



    def execute_scaling(
        self, 
        service: ServiceState, 
        target_replicas: int, 
        current_replicas: int,
        metrics: dict,
        action_name: str
    ) -> bool:
        """Execute scaling action for a service (RL model decides, no cooldown interference).

        ⚠️ Philosophy: Model RL training already handles flapping prevention via reward function.
        Direct execution without cooldown allows objective evaluation of model behavior.

        Args:
            service: Service state object
            target_replicas: Target replica count from model
            current_replicas: Current replica count
            metrics: Collected metrics (unused in this minimal mode)
            action_name: Scaling action ("scale_up", "scale_down", "stay")

        Returns:
            True if scaling executed or not needed
        """
        if action_name == "stay" or target_replicas == current_replicas:
            logger.debug(
                f"[{service.service_name}] No scaling needed (action=stay or target equals current)"
            )
            return True

        # Execute scaling directly as model decides (no cooldown interference)
        success = self.k8s_scaler.scale_deployment(
            target_replicas, service.deployment_name
        )

        if success:
            logger.info(
                f"[{service.service_name}] ✅ Scaled {action_name}: {current_replicas} → {target_replicas}"
            )
            return True

        return False

    def process_service(self, service: ServiceState) -> bool:
        """Process one service: collect metrics, decide, and execute scaling.

        Args:
            service: Service state object

        Returns:
            True if processing succeeded, False if critical error
        """
        service.iteration += 1

        logger.info(
            f"========== Iteration {service.iteration} [{service.service_name}] =========="
        )

        # Get current replicas
        current_replicas = self.k8s_scaler.get_replicas(service.deployment_name)
        if current_replicas is None:
            logger.error(
                f"[{service.service_name}] Failed to get current replicas"
            )
            return False

        # Collect metrics
        metrics = self.collect_service_metrics(service)
        if metrics is None:
            logger.error(f"[{service.service_name}] Failed to collect metrics")
            return False

        # Log raw metrics
        logger.info(
            f"[{service.service_name}] Raw metrics - "
            f"RPS: {metrics.get('rps'):.2f}, CPU: {metrics.get('cpu'):.2f}, "
            f"Memory: {metrics.get('memory'):.3f}, Latency: {metrics.get('latency'):.2f}ms, "
            f"Replicas: {int(metrics.get('replicas', 0)) if metrics.get('replicas') else 'N/A'}"
        )

        # Make scaling decision
        target_replicas, action_name, normalized = self.make_scaling_decision(
            service, metrics, current_replicas
        )

        # Log decision
        logger.info(
            f"[{service.service_name}] RL Decision - Action: {action_name}, "
            f"Current: {current_replicas}, Target: {target_replicas}"
        )

        # Log normalized state
        if normalized:
            logger.info(
                f"[{service.service_name}] Normalized State - "
                f"RPS_norm: {normalized.get('rps_norm'):.3f}, "
                f"CPU_norm: {normalized.get('cpu_norm'):.3f}, "
                f"Memory_norm: {normalized.get('memory_norm'):.3f}, "
                f"Latency_norm: {normalized.get('latency_norm'):.3f}, "
                f"Replicas_norm: {normalized.get('replicas_norm'):.3f}, "
                f"DeltaRPS_norm: {normalized.get('delta_rps_norm'):.3f}"
            )

        # Execute scaling if needed (with RL-aware, directional cooldown)
        if self.execute_scaling(service, target_replicas, current_replicas, metrics, action_name):
            # Get final replicas after scaling (may differ from target due to adaptive step)
            final_replicas = self.k8s_scaler.get_replicas(service.deployment_name)
            action_symbol = (
                "↑" if final_replicas > current_replicas
                else "↓" if final_replicas < current_replicas
                else "→"
            )
            logger.info(
                f"[{service.service_name}] 🎯 Action={action_name} {action_symbol} "
                f"Replicas: {current_replicas}→{final_replicas} ✅ SCALED"
            )
        else:
            logger.info(
                f"[{service.service_name}] Action={action_name} - "
                f"No scaling (cooldown or no change needed)"
            )

        # Update previous RPS for next iteration
        service.previous_rps = metrics.get("rps", 0.0) or 0.0

        logger.info(
            f"========== Iteration {service.iteration} [{service.service_name}] Complete =========="
        )

        return True

    def run_loop_iteration(self) -> bool:
        """Run one full iteration for all services.

        Returns:
            True if iteration succeeded, False if critical error
        """
        self.global_iteration += 1
        logger.info(f"\n{'='*80}")
        logger.info(f"Global Iteration {self.global_iteration} - Processing {len(TARGET_SERVICES)} services")
        logger.info(f"{'='*80}\n")

        all_succeeded = True
        for service_name in TARGET_SERVICES:
            service = self.service_states[service_name]
            try:
                success = self.process_service(service)
                if not success:
                    logger.error(
                        f"[{service_name}] Processing failed, continuing with next service..."
                    )
                    all_succeeded = False
            except Exception as e:
                logger.error(
                    f"[{service_name}] Unexpected error: {e}", exc_info=True
                )
                all_succeeded = False

        return all_succeeded

    def run(self, interval: int = 15):
        """Run autoscaler continuously.

        Args:
            interval: Seconds between each global iteration
        """
        logger.info(
            f"Starting Centralized RL Autoscaler for {len(TARGET_SERVICES)} services (interval={interval}s)..."
        )
        logger.info(f"Services: {TARGET_SERVICES}")

        # Check Prometheus health first
        if not self.prom_client.health_check():
            logger.warning("Prometheus health check failed, continuing anyway...")

        try:
            while True:
                try:
                    success = self.run_loop_iteration()
                    if not success:
                        logger.error("Iteration had errors, retrying...")

                except Exception as e:
                    logger.error(f"Unexpected error in loop: {e}", exc_info=True)

                # Wait before next iteration
                logger.debug(f"Sleeping for {interval}s...")
                time.sleep(interval)

        except KeyboardInterrupt:
            logger.info("Received SIGTERM, shutting down gracefully...")
        except Exception as e:
            logger.error(f"Fatal error: {e}", exc_info=True)
            sys.exit(1)


def main():
    """Main entry point."""
    try:
        autoscaler = RLAutoscaler()
        autoscaler.run(interval=15)
    except Exception as e:
        logger.error(f"Failed to start autoscaler: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()


if __name__ == "__main__":
    main()
