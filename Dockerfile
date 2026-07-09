FROM python:3.11-slim

# Set environment variables
# PYTHONUNBUFFERED=1 ensures logs are printed to stdout/stderr in real-time
ENV PYTHONUNBUFFERED=1 \
    LURKER_PORT=7777 \
    LURKER_HOST=0.0.0.0 \
    LURKER_OUTPUT_DIR=/data

# Create output directory for received files
RUN mkdir -p /data

# Set the working directory
WORKDIR /app

# Copy application script
COPY lurker.py .

# Expose port (corresponds to default LURKER_PORT)
EXPOSE 7777

# Run the application
CMD ["python", "lurker.py"]
