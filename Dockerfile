FROM node:20.18-slim

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 \
        python3-pip \
        python3-venv \
        git \
        chromium \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Create a virtual environment
RUN python3 -m venv /opt/venv

# Set environment variables
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium \
    NODE_ENV=production \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy and install Python dependencies without pip cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy and install Node.js dependencies for website-to-pdf
COPY scripts/website-to-pdf/package*.json scripts/website-to-pdf/
RUN cd scripts/website-to-pdf && npm install --verbose

# Copy and install Node.js dependencies for website-to-src
COPY scripts/website-to-src/package*.json scripts/website-to-src/
RUN cd scripts/website-to-src && npm install --verbose

# Copy the rest of the application code
COPY . .

# Expose the Flask run port (optional, adjust as needed)
EXPOSE ${FLASK_RUN_PORT}

# Command to run the application
CMD ["gunicorn", "--worker-class", "gevent", "--workers", "2", "--bind", "0.0.0.0:3002", "--reload", "app:app"]