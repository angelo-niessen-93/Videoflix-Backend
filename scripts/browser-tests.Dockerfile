# Optional test tooling only; the application uses backend.Dockerfile.
FROM python:3.12-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg nodejs npm \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements*.txt .
RUN pip install --no-cache-dir -r requirements-browser.txt \
    && playwright install --with-deps chromium \
    && npm install --prefix /root/.vscode/extensions/ritwickdey.liveserver-5.7.10 live-server
COPY . .
ENV DJANGO_SETTINGS_MODULE=config.test_settings VIDEOFLIX_BROWSER_TESTS=1 PLAYWRIGHT_CHANNEL=chromium
CMD ["sh", "-c", "python -m coverage run --source=accounts,videos,config manage.py test tests --settings=config.test_settings --noinput && python -m coverage report"]
