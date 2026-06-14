FROM python:3.12-slim AS builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

COPY kubectl_analytics/ ./kubectl_analytics/
COPY pyproject.toml .
RUN pip install --no-cache-dir --prefix=/install --no-deps .


FROM python:3.12-slim

COPY --from=builder /install /usr/local

ENTRYPOINT ["kubectl-analytics"]
