"""Main entry point for RL Kubernetes autoscaler."""

import logging
import sys
import time
from typing import Optional
import numpy as np

from config import (
    NAMESPACE,
    DEPLOYMENT_NAME,
    TARGET_DEPLOYMENT,
    TARGET_SERVICE,
    COOLDOWN_SECONDS,
    MODEL_PATH,
    MIN_REPLICAS,
    MAX_REPLICAS,
    LOG_LEVEL,
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


class RLAutoscaler:
    """RL-based Kubernetes autoscaler."""

    def __init__(self):
        """Initialize autoscaler components."""
        logger.info("Initializing RL Autoscaler...")

        # Initialize Prometheus client
        self.prom_client = PrometheusClient()

        # Initialize Kubernetes scaler
        self.k8s_scaler = KubernetesScaler(NAMESPACE, DEPLOYMENT_NAME)

        # Load RL model
        try:
            self.model = RLModel(MODEL_PATH)
            logger.info(f"RL Model loaded: {self.model}")
        except Exception as e:
            logger.error(f"Failed to load RL model: {e}")
            raise

        # State tracking
        self.previous_rps = 0.0
        self.last_scale_time = 0
        self.iteration = 0

        logger.info("RL Autoscaler initialized successfully")

    def collect_metrics(self) -> Optional[dict]:
        """Collect metrics from Prometheus.

        Returns:
            Dict with metrics, or None if collection failed
        """
        metrics = self.prom_client.query_all_metrics()

        # Check if we have valid data
        if not all(v is not None for v in metrics.values()):
            logger.warning(f"Some metrics are missing: {metrics}")

        return metrics

    def make_scaling_decision(
        self, metrics: dict, current_replicas: int
    ) -> tuple[int, str, dict]:
        """Use RL model to make scaling decision.

        Args:
            metrics: Collected metrics
            current_replicas: Current replica count

        Returns:
            Tuple of (target_replicas, action_name, normalized_state_dict)
        """
        try:
            # Normalize metrics
            state, normalized = normalize_metrics(metrics, self.previous_rps)

            logger.debug(f"Normalized state: {normalized}")

            # Get action from RL model
            action, _ = self.model.predict(state, deterministic=True)

            # Convert action to scaling decision
            target_replicas, action_name = action_to_scaling(
                action, current_replicas, MIN_REPLICAS, MAX_REPLICAS
            )

            return target_replicas, action_name, normalized

        except Exception as e:
            logger.error(f"Failed to make scaling decision: {e}")
            return current_replicas, "ERROR", {}

    def should_cooldown(self) -> bool:
        """Check if in cooldown period.

        Returns:
            True if in cooldown, False otherwise
        """
        elapsed = time.time() - self.last_scale_time
        if elapsed < COOLDOWN_SECONDS:
            logger.info(
                f"In cooldown period: {COOLDOWN_SECONDS - elapsed:.1f}s remaining"
            )
            return True
        return False

    def execute_scaling(self, target_replicas: int, current_replicas: int) -> bool:
        """Execute scaling action if needed.

        Args:
            target_replicas: Target replica count
            current_replicas: Current replica count

        Returns:
            True if scaling executed or not needed
        """
        if target_replicas == current_replicas:
            logger.info("No scaling needed (target equals current)")
            return True

        if self.should_cooldown():
            return False

        # Execute scaling
        success = self.k8s_scaler.scale_deployment(target_replicas)

        if success:
            self.last_scale_time = time.time()
            return True

        return False

    def run_loop_iteration(self) -> bool:
        """Run one iteration of the autoscaler loop.

        Returns:
            True if iteration succeeded, False if critical error
        """
        self.iteration += 1

        logger.info(f"========== Iteration {self.iteration} [{DEPLOYMENT_NAME}] ==========")

        # Get current replicas
        current_replicas = self.k8s_scaler.get_replicas()
        if current_replicas is None:
            logger.error(f"[{DEPLOYMENT_NAME}] Failed to get current replicas")
            return False

        # Collect metrics
        metrics = self.collect_metrics()
        if metrics is None:
            logger.error("Failed to collect metrics")
            return False

        # Log raw metrics
        logger.info(
            f"[{DEPLOYMENT_NAME}] Raw metrics - RPS: {metrics.get('rps'):.2f}, CPU: {metrics.get('cpu'):.2f}, "
            f"Memory: {metrics.get('memory'):.3f}, Latency: {metrics.get('latency'):.2f}ms, "
            f"Replicas: {int(metrics.get('replicas', 0)) if metrics.get('replicas') else 'N/A'}"
        )

        # Make scaling decision
        target_replicas, action_name, normalized = self.make_scaling_decision(
            metrics, current_replicas
        )

        # Log decision
        logger.info(
            f"[{DEPLOYMENT_NAME}] RL Decision - Action: {action_name}, Current: {current_replicas}, "
            f"Target: {target_replicas}"
        )

        # Log normalized state
        if normalized:
            logger.info(
                f"[{DEPLOYMENT_NAME}] Normalized State - RPS_norm: {normalized.get('rps_norm'):.3f}, "
                f"CPU_norm: {normalized.get('cpu_norm'):.3f}, "
                f"Memory_norm: {normalized.get('memory_norm'):.3f}, "
                f"Latency_norm: {normalized.get('latency_norm'):.3f}, "
                f"Replicas_norm: {normalized.get('replicas_norm'):.3f}, "
                f"DeltaRPS_norm: {normalized.get('delta_rps_norm'):.3f}"
            )

        # Execute scaling if needed
        if self.execute_scaling(target_replicas, current_replicas):
            action_symbol = "↑" if target_replicas > current_replicas else "↓" if target_replicas < current_replicas else "→"
            logger.info(
                f"[{DEPLOYMENT_NAME}] 🎯 Action={action_name} {action_symbol} "
                f"Replicas: {current_replicas}→{target_replicas} ✅ SCALED"
            )
        else:
            logger.info(
                f"[{DEPLOYMENT_NAME}] Action={action_name} - No scaling (cooldown or no change needed)"
            )

        # Update previous RPS for next iteration
        self.previous_rps = metrics.get("rps", 0.0) or 0.0

        logger.info(f"========== Iteration {self.iteration} [{DEPLOYMENT_NAME}] Complete ==========")

        return True

    def run(self, interval: int = 30):
        """Run autoscaler continuously.

        Args:
            interval: Seconds between each iteration
        """
        logger.info(f"Starting RL Autoscaler (interval={interval}s)...")

        # Check Prometheus health first
        if not self.prom_client.health_check():
            logger.warning("Prometheus health check failed, continuing anyway...")

        try:
            while True:
                try:
                    success = self.run_loop_iteration()
                    if not success:
                        logger.error("Iteration failed, retrying...")

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
