FROM python:3.9-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y wget tar && rm -rf /var/lib/apt/lists/*

# Copy the application files
COPY app.py pr1.txt pr2.txt requirements.txt ./

# Install Python packages
RUN pip install --no-cache-dir -r requirements.txt

# Create necessary directories
RUN mkdir -p /root/.local/share/embykeeper/hf/version

# Expose the port
EXPOSE 7860

# Run the application
CMD ["python", "-u", "app.py"]
