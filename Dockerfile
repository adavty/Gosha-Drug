FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
RUN pip install --no-cache-dir '.[postgres]'
RUN useradd --create-home appuser && mkdir -p /var/lib/gosha && chown appuser:appuser /var/lib/gosha
USER appuser
EXPOSE 8080
CMD ["gosha-server", "--db", "/tmp/gosha-demo.db", "--host", "0.0.0.0", "--port", "8080"]
