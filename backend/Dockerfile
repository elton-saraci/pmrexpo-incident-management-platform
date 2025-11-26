# syntax=docker/dockerfile:1

# 1. Base image
FROM python:3.12-slim AS base

# Prevent Python from writing .pyc files & enable unbuffered logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 2. Work directory inside the container
WORKDIR /app

# 3. System dependencies (only if you need build tools, else you can remove build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
  && rm -rf /var/lib/apt/lists/*

# 4. Install Python dependencies
# Copy only requirements first to leverage Docker layer caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the rest of your backend source code
COPY . .

# 6. Environment variables for Flask
# If you use an application factory, adjust FLASK_APP accordingly
ENV FLASK_ENV=production \
    FLASK_APP=app.py

# 7. Expose the port your Flask app will listen on
EXPOSE 8080

# 8. Start the app with Gunicorn (recommended for production)
# If your app object is not named "app" or file not "app.py", adjust "app:app"
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "app:app"]
