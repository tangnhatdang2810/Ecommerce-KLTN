"""Utility functions for RL autoscaler."""

import logging
import numpy as np
from typing import Dict, Tuple
from config import NORMALIZATION

logger = logging.getLogger(__name__)


def normalize_metrics(
    metrics: Dict[str, float], previous_rps: float = 0.0
) -> Tuple[np.ndarray, Dict[str, float]]:
    """Normalize metrics for RL model input.

    Args:
        metrics: Raw metrics dict (rps, cpu, memory, latency, replicas)
        previous_rps: Previous RPS value for delta calculation

    Returns:
        Tuple of (normalized_state array, normalized_dict)
    """
    normalized = {}

    # RPS normalization
    rps = metrics.get("rps", 0.0) or 0.0
    rps_norm = rps / NORMALIZATION["rps"]
    normalized["rps_norm"] = float(np.clip(rps_norm, -1, 1))

    # CPU normalization
    cpu = metrics.get("cpu", 0.0) or 0.0
    cpu_norm = cpu / NORMALIZATION["cpu"]
    normalized["cpu_norm"] = float(np.clip(cpu_norm, 0, 1))

    # Memory normalization (clamp max 0.8)
    memory = metrics.get("memory", 0.0) or 0.0
    memory_norm = memory / NORMALIZATION["memory"]
    normalized["memory_norm"] = float(np.clip(memory_norm, 0, 0.8))

    # Latency normalization
    latency = metrics.get("latency", 0.0) or 0.0
    latency_norm = latency / NORMALIZATION["latency"]
    normalized["latency_norm"] = float(np.clip(latency_norm, 0, 1))

    # Replicas normalization (runtime max = 7)
    replicas = metrics.get("replicas", 1.0) or 1.0
    replicas_norm = replicas / NORMALIZATION["replicas"]
    normalized["replicas_norm"] = float(np.clip(replicas_norm, 0, 1))

    # Delta RPS
    delta_rps = rps - previous_rps
    delta_rps_norm = delta_rps / NORMALIZATION["rps"]
    normalized["delta_rps_norm"] = float(np.clip(delta_rps_norm, -1, 1))

    # Construct state array for RL model
    # Order: [rps_norm, cpu_norm, memory_norm, latency_norm, replicas_norm, delta_rps_norm]
    state = np.array(
        [
            normalized["rps_norm"],
            normalized["cpu_norm"],
            normalized["memory_norm"],
            normalized["latency_norm"],
            normalized["replicas_norm"],
            normalized["delta_rps_norm"],
        ],
        dtype=np.float32,
    )

    return state, normalized


def action_to_scaling(action: int, current_replicas: int, min_replicas: int, max_replicas: int) -> Tuple[int, str]:
    """Convert RL action to scaling decision.

    Args:
        action: RL model action (0=KEEP, 1=SCALE_UP, 2=SCALE_DOWN)
        current_replicas: Current number of replicas
        min_replicas: Minimum allowed replicas
        max_replicas: Maximum allowed replicas

    Returns:
        Tuple of (target_replicas, action_name)
    """
    action_map = {0: "KEEP", 1: "SCALE_UP", 2: "SCALE_DOWN"}
    action_name = action_map.get(action, "UNKNOWN")

    if action == 0:  # KEEP
        return current_replicas, action_name
    elif action == 1:  # SCALE UP
        target = min(current_replicas + 1, max_replicas)
        return target, action_name
    elif action == 2:  # SCALE DOWN
        target = max(current_replicas - 1, min_replicas)
        return target, action_name
    else:
        logger.warning(f"Unknown action: {action}, keeping current replicas")
        return current_replicas, "UNKNOWN"


def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
    """Safely divide two numbers.

    Args:
        numerator: Numerator
        denominator: Denominator
        default: Default value if denominator is zero or None

    Returns:
        Result of division or default value
    """
    if denominator is None or denominator == 0:
        return default
    try:
        return float(numerator) / float(denominator)
    except (TypeError, ValueError, ZeroDivisionError):
        return default
