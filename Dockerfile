FROM python:3.11-slim

WORKDIR /app

# Install Tk (note: GUI requires a display; not available in headless containers by default)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-tk \
    && rm -rf /var/lib/apt/lists/*

# Copy and install dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the project
COPY . /app

# Default command (GUI will not show in headless containers)
CMD ["python", "app/app_v2.py"]
