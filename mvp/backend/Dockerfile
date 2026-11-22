FROM python:3.12-slim

# Python 3.12: la versión con la que se corren los tests (los pines de requirements.txt
# no instalan en 3.13, ver README). Fase 2, P01.
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY scripts ./scripts
# Fase 2, P02: migraciones de Alembic. El backend aplica `upgrade head` al arrancar.
COPY alembic.ini .
COPY migrations ./migrations

# Paquete de reproducibilidad: commit con el que se construyó la imagen (GET /health y
# GET /version lo devuelven). docker compose lo pasa desde GIT_COMMIT; a mano:
#   docker build --build-arg GIT_COMMIT=$(git rev-parse HEAD) backend
ARG GIT_COMMIT=desconocido
ENV GIT_COMMIT=$GIT_COMMIT

EXPOSE 8000
# PORT lo fija el servicio de hosting (Render/Railway); en local queda 8000.
# --timeout-keep-alive 15 (default de uvicorn: 5 s): mayor que el intervalo entre lotes de la
# captura (5 s, syncQueue.ts), para que la conexión de un cliente pueda reutilizarse entre lotes.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*' --timeout-keep-alive 15"]
