# Use Python 3.11 slim base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PORT=5001

# Install system dependencies for OpenCV and face recognition
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    libglib2.0-0 \
    libgl1 \
    libpq-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code (exclude frontend for separate build)
COPY deployment/ ./deployment/
COPY cameras/ ./cameras/
COPY face_recognition/ ./face_recognition/
COPY codes/ ./codes/
COPY Attendance/ ./Attendance/
COPY StudentDetails/ ./StudentDetails/
COPY model/ ./model/
COPY database/ ./database/
COPY *.py ./

# Copy tests (optional, for verification)
COPY tests/ ./tests/

# Create necessary directories
RUN mkdir -p TrainingImage model logs

# Expose port
EXPOSE 5001

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:5001/api/health')" || exit 1

# Run the application
CMD ["python", "deployment/api.py"]
