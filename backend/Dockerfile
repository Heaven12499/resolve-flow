FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt ./
# Keep the image build aligned with the documented local setup.  The default
# PyPI index avoids making a production build depend on a regional mirror.
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
