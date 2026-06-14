FROM python:3.11-slim

WORKDIR /app

# Core deps first for layer caching.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# To bake in the Classiq backend, uncomment (and provide credentials at runtime):
# COPY requirements-classiq.txt .
# RUN pip install --no-cache-dir -r requirements-classiq.txt

COPY app ./app

ENV QUANTUM_BACKEND=local \
    STORE_BACKEND=sql \
    DATABASE_URL=sqlite:///./qimvp.db

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
