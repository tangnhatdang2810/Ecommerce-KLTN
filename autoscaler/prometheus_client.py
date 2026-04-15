"""Prometheus metrics client."""

import requests
import logging
from typing import Dict, Optional
from config import PROM_URL, METRIC_QUERIES, PROM_QUERY_TIMEOUT, TARGET_SERVICE, TARGET_DEPLOYMENT

logger = logging.getLogger(__name__)


class PrometheusClient:
    """Client for querying Prometheus metrics."""

    def __init__(self, base_url: str = PROM_URL, target_service: str = TARGET_SERVICE):
        """Initialize Prometheus client.

        Args:
            base_url: Prometheus endpoint URL
            target_service: Target service name for filtering metrics
        """
        self.base_url = base_url
        self.query_endpoint = f"{base_url}/api/v1/query"
        self.target_service = target_service

    def query_metric(self, metric_name: str) -> Optional[float]:
        """Query a single metric from Prometheus.

        Args:
            metric_name: Name of the metric (key in METRIC_QUERIES)

        Returns:
            Metric value as float, or None if query fails
        """
        if metric_name not in METRIC_QUERIES:
            logger.warning(f"Unknown metric: {metric_name}")
            return None

        query = METRIC_QUERIES[metric_name]

        try:
            response = requests.get(
                self.query_endpoint,
                params={"query": query},
                timeout=PROM_QUERY_TIMEOUT,
            )
            response.raise_for_status()

            data = response.json()
            if data.get("status") != "success":
                logger.error(f"Prometheus error: {data.get('error', 'Unknown error')}")
                return None

            results = data.get("data", {}).get("result", [])
            if not results:
                logger.warning(f"No data for metric: {metric_name}")
                return None

            # Extract value from first result
            value = results[0].get("value", [None, None])[1]
            if value is None:
                return None

            try:
                value_float = float(value)
                
                # Convert CPU metric to match training scale (percent)
                if metric_name == "cpu":
                    value_float = value_float * 100
                
                return value_float
            except (ValueError, TypeError):
                logger.error(f"Cannot convert metric value to float: {value}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to query {metric_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error querying {metric_name}: {e}")
            return None

    def query_all_metrics(self) -> Dict[str, Optional[float]]:
        """Query all metrics at once.

        Returns:
            Dictionary with metric names as keys and values (or None if failed)
        """
        metrics = {}
        for metric_name in METRIC_QUERIES.keys():
            metrics[metric_name] = self.query_metric(metric_name)

        return metrics

    def health_check(self) -> bool:
        """Check if Prometheus is healthy.

        Returns:
            True if Prometheus is reachable, False otherwise
        """
        try:
            response = requests.get(
                f"{self.base_url}/-/healthy",
                timeout=PROM_QUERY_TIMEOUT,
            )
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            logger.error(f"Prometheus health check failed: {e}")
            return False
