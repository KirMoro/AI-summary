FROM python:3.12-slim

# Install system dependencies (ffmpeg for audio processing, yt-dlp needs it)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Make start script executable
RUN chmod +x start.sh

EXPOSE 8000

CMD ["bash", "start.sh"]
