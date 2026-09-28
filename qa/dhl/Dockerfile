FROM node:22-bookworm
# Dependency installation is the only network-enabled phase. No application runs here.
RUN printf '#!/bin/sh\nexit 101\n' > /usr/sbin/policy-rc.d && chmod +x /usr/sbin/policy-rc.d
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv postgresql-15 && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:/usr/lib/postgresql/15/bin:${PATH}" PLAYWRIGHT_BROWSERS_PATH=/opt/browsers
COPY target/shopsoma-backend/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt playwright==1.55.0 pytest-cov==6.0.0
RUN playwright install --with-deps chromium
COPY target/shopsoma-frontend/package*.json /target/shopsoma-frontend/
RUN cd /target/shopsoma-frontend && npm ci
COPY target/shopsoma-backend /target/shopsoma-backend
COPY target/shopsoma-frontend /target/shopsoma-frontend
COPY harness/qa/dhl /harness
RUN useradd -m qa && mkdir /evidence && chown -R qa:qa /target /harness /evidence /opt/browsers
USER qa
WORKDIR /target/shopsoma-backend
ENV ENVIRONMENT=test USE_LOCAL_STORAGE=true ALLOW_LOCAL_STORAGE_IN_NON_DEV=true \
    LOCAL_UPLOAD_DIR=/tmp/dhl-uploads ALLOWED_ORIGINS='["http://127.0.0.1:5173"]' \
    VITE_API_BASE_URL=http://127.0.0.1:8000/api/v1 \
    DHL_ENABLED=false DHL_DOMESTIC_WORKFLOW_ENABLED=false \
    DHL_DOMESTIC_PROVIDER_CALLS_ENABLED=false DHL_DOMESTIC_CHECKOUT_ENABLED=false \
    PYTHONPATH=/target/shopsoma-backend:/harness PYTHONDONTWRITEBYTECODE=1
ENTRYPOINT ["python", "/harness/run.py"]
