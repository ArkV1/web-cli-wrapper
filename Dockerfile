FROM --platform=arm64 node:20-slim

# Install system dependencies including chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \
    git \
    chromium \
    && rm -rf /var/lib/apt/lists/* \
    && python3 -m venv /opt/venv

ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH" \
    PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true \
    PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium

WORKDIR /app

# Copy entire project
COPY . .

# Install dependencies with better error handling and verbosity
RUN pip install -r requirements.txt && \
    cd scripts/website-to-pdf && \
    npm install --verbose && \
    cd ../website-to-src && \
    npm install --verbose

CMD ["flask", "run"]
