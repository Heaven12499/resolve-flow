FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
# Demo RAG uses a local Chinese feature vectorizer, so no model or GPU packages
# need to be downloaded at image build or first use.
RUN pip install --no-cache-dir \
        --index-url https://mirrors.aliyun.com/pypi/simple \
        --extra-index-url https://pypi.org/simple \
        -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
