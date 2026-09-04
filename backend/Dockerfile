FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
# Install general dependencies from the default PyPI index.
# The embedding service explicitly runs on CPU. Install the CPU-only PyTorch
# wheel before sentence-transformers resolves its optional torch dependency,
# otherwise PyPI can select several gigabytes of unused CUDA runtime packages.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
