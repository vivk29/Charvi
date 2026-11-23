FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
RUN useradd --create-home --uid 10001 charvi
COPY pyproject.toml README.md ./
COPY apps/api ./apps/api
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic pydantic-settings
ENV PYTHONPATH=/app/apps/api
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "charvi_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
