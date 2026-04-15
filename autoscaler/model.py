"""RL Model loading and prediction."""

import logging
import os
from typing import Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


class RLModel:
    """RL Model wrapper for PPO and A2C."""

    def __init__(self, model_path: str):
        """Initialize RL model.

        Args:
            model_path: Path to saved model zip file

        Raises:
            FileNotFoundError: If model file doesn't exist
            ImportError: If stable_baselines3 is not installed
        """
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")

        try:
            from stable_baselines3 import PPO, A2C
        except ImportError:
            raise ImportError("stable_baselines3 not installed. Run: pip install stable-baselines3")

        self.model_path = model_path
        self.model = None
        self.algo_type = None

        # Load model
        try:
            # Try PPO first
            self.model = PPO.load(model_path)
            self.algo_type = "PPO"
            logger.info(f"Loaded PPO model from {model_path}")
        except Exception as e:
            logger.debug(f"PPO load failed: {e}, trying A2C...")
            try:
                self.model = A2C.load(model_path)
                self.algo_type = "A2C"
                logger.info(f"Loaded A2C model from {model_path}")
            except Exception as e2:
                logger.error(f"Failed to load model: {e2}")
                raise

    def predict(self, state: np.ndarray, deterministic: bool = True) -> Tuple[int, Optional[np.ndarray]]:
        """Predict action from state.

        Args:
            state: Input state (normalized)
            deterministic: Whether to use deterministic policy

        Returns:
            Tuple of (action, state_value or None)
        """
        if self.model is None:
            logger.error("Model not loaded")
            raise RuntimeError("Model not loaded")

        try:
            # Ensure state is proper shape and type
            if isinstance(state, list):
                state = np.array(state, dtype=np.float32)
            elif not isinstance(state, np.ndarray):
                state = np.array([state], dtype=np.float32)

            if state.ndim == 1:
                state = state.reshape(1, -1)

            action, _ = self.model.predict(state, deterministic=deterministic)

            # Convert numpy scalar to int
            action = int(action[0]) if isinstance(action, np.ndarray) else int(action)

            return action, None

        except Exception as e:
            logger.error(f"Prediction failed: {e}")
            raise

    def get_algo_type(self) -> str:
        """Get algorithm type.

        Returns:
            Algorithm type (PPO or A2C)
        """
        return self.algo_type

    def __repr__(self) -> str:
        return f"RLModel({self.algo_type}, path={self.model_path})"
