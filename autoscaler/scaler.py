"""Kubernetes deployment scaler."""

import logging
from typing import Optional, Tuple
from kubernetes import client, config

logger = logging.getLogger(__name__)


class KubernetesScaler:
    """Kubernetes deployment scaler."""

    def __init__(self, namespace: str, deployment_name: str):
        """Initialize Kubernetes scaler.

        Args:
            namespace: Kubernetes namespace
            deployment_name: Deployment name

        Raises:
            Exception: If not running in cluster or config load fails
        """
        self.namespace = namespace
        self.deployment_name = deployment_name

        try:
            config.load_incluster_config()
            logger.info("Loaded in-cluster config")
        except Exception as e:
            logger.warning(f"In-cluster config load failed: {e}, trying default config...")
            config.load_kube_config()
            logger.info("Loaded default kubeconfig")

        self.apps_api = client.AppsV1Api()

    def get_replicas(self) -> Optional[int]:
        """Get current number of replicas for deployment.

        Returns:
            Current replica count, or None if failed
        """
        try:
            deployment = self.apps_api.read_namespaced_deployment(
                self.deployment_name, self.namespace
            )
            replicas = deployment.spec.replicas or 1
            logger.debug(f"Current replicas: {replicas}")
            return replicas
        except Exception as e:
            logger.error(f"Failed to get replicas: {e}")
            return None

    def scale_deployment(self, target_replicas: int) -> bool:
        """Scale deployment to target replicas.

        Args:
            target_replicas: Target number of replicas

        Returns:
            True if scaling succeeded, False otherwise
        """
        try:
            deployment = self.apps_api.read_namespaced_deployment(
                self.deployment_name, self.namespace
            )

            current_replicas = deployment.spec.replicas or 1

            if current_replicas == target_replicas:
                logger.info(f"Already at {target_replicas} replicas, no scaling needed")
                return True

            # Patch the deployment spec
            deployment.spec.replicas = target_replicas
            self.apps_api.patch_namespaced_deployment(
                self.deployment_name, self.namespace, deployment
            )

            logger.info(
                f"Scaled deployment from {current_replicas} to {target_replicas} replicas"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to scale deployment: {e}")
            return False

    def get_deployment_info(self) -> Optional[dict]:
        """Get deployment information.

        Returns:
            Dictionary with deployment info, or None if failed
        """
        try:
            deployment = self.apps_api.read_namespaced_deployment(
                self.deployment_name, self.namespace
            )

            return {
                "name": deployment.metadata.name,
                "namespace": deployment.metadata.namespace,
                "replicas": deployment.spec.replicas or 1,
                "ready_replicas": deployment.status.ready_replicas or 0,
                "available_replicas": deployment.status.available_replicas or 0,
            }
        except Exception as e:
            logger.error(f"Failed to get deployment info: {e}")
            return None

    def __repr__(self) -> str:
        return f"KubernetesScaler(namespace={self.namespace}, deployment={self.deployment_name})"
