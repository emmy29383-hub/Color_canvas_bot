FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for PIL
RUN apt-get update && apt-get install -y \
    gcc \
    libjpeg-dev \
    libpng-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Set environment variables
ENV PYTHONUNBUFFERED=1

CMD ["python", "-u", "main.py"]
