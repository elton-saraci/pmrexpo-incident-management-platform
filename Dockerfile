FROM python:3.11-slim

# System dependencies for Pillow, Torch, etc.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    && rm -rf /var/lib/apt/lists/*

# Working directory inside the container
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (including main.py, models/, etc.)
COPY . .

# Expose FastAPI port
EXPOSE 8000

# Start server via python -m uvicorn (more robust than calling "uvicorn" directly)
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]