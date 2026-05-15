FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN useradd -m -u 1000 autoscaler && chown -R autoscaler:autoscaler /app

# Copy requirements first (better Docker cache layer)
COPY requirements.txt .

# Install dependencies with torch from PyTorch official index
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    --extra-index-url https://pypi.org/simple/ \
    -r requirements.txt

# Copy pre-trained RL models (BEFORE application code)
COPY --chown=autoscaler:autoscaler models/ models/

# Copy application code
COPY --chown=autoscaler:autoscaler agent.py .

# Switch to non-root user
USER autoscaler

# Run the agent
CMD ["python", "-u", "agent.py"]
