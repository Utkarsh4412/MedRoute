FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Download sentence-transformer model at build time (not at runtime)
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copy everything
COPY . .

# Expose API port
EXPOSE 8000

# Start server
CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000"]
