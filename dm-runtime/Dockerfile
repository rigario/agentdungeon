FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HERMES_HOME=/root/.hermes

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vendor/hermes-agent /opt/hermes-agent
RUN test -f /opt/hermes-agent/pyproject.toml \
    && pip install --no-cache-dir /opt/hermes-agent \
    || (echo 'Missing vendored Hermes source at dm-runtime/vendor/hermes-agent. Run scripts/sync-hermes-agent-into-dm-runtime.sh before building.' && exit 1)

COPY hermes-home /opt/d20-hermes-home
COPY docker-entrypoint.sh /usr/local/bin/d20-dm-entrypoint.sh
RUN chmod +x /usr/local/bin/d20-dm-entrypoint.sh

COPY . .

EXPOSE 8610

ENTRYPOINT ["/usr/local/bin/d20-dm-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8610"]
