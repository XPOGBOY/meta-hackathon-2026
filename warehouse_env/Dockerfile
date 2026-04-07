FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire package
COPY . /app/warehouse_env/

# Add the parent of the package to PYTHONPATH
ENV PYTHONPATH=/app

# Expose port required by Hugging Face Spaces
EXPOSE 7860

CMD ["uvicorn", "warehouse_env.server.app:app", "--host", "0.0.0.0", "--port", "7860"]
