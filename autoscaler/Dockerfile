FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

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
