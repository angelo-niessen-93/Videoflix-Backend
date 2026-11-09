# Based on Developer-Akademie-Backendkurs/material.videoflix-docker-files.
FROM python:3.12-alpine

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY . .

RUN apk add --no-cache bash postgresql-client ffmpeg \
    && apk add --no-cache --virtual .build-deps gcc musl-dev postgresql-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apk del .build-deps \
    && sed -i 's/\r$//' backend.entrypoint.sh \
    && chmod +x backend.entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./backend.entrypoint.sh"]
