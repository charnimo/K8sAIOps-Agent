FROM python:3.12-slim

LABEL maintainer="AIOps Platform"
LABEL description="Kubernetes Real-Time Monitoring & Notification Service"

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY monitor.py .

# Non-root user
RUN groupadd -r aiops && useradd -r -g aiops -u 1000 aiops
USER aiops

EXPOSE 8765 8080

CMD ["python", "-u", "monitor.py"]
