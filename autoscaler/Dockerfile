FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install torch from PyTorch official index FIRST
# Using --index-url to get CPU-only build (~1.5-2GB instead of 3-4GB with CUDA)
RUN pip install --no-cache-dir \
    --index-url https://download.pytorch.org/whl/cpu \
    torch==2.0.1+cpu

# Install rest of dependencies from requirements.txt
# Using --no-deps to skip torch dependency (already installed above)
# This prevents pip from trying to pull full GPU torch from default PyPI
RUN pip install --no-cache-dir -r requirements.txt --no-deps

# Copy application code
COPY config.py .
COPY prometheus_client.py .
COPY scaler.py .
COPY model.py .
COPY utils.py .
COPY main.py .

# Copy pre-trained RL models
COPY models/ models/

# Run the application
CMD ["python", "-u", "main.py"]
