# Use Python 3.9 as base image
FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies required for numpy and audio processing
RUN apt-get update && apt-get install -y \
    build-essential \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code
COPY sesame_test/ ./sesame_test/
COPY sesame_ai/ ./sesame_ai/

# Create static directory inside sesame_test if it doesn't exist
RUN mkdir -p ./sesame_test/static

# Expose the port the app runs on
EXPOSE 8000

# Set environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# Command to run the application
CMD ["uvicorn", "sesame_test.app:app", "--host", "0.0.0.0", "--port", "8000"] 