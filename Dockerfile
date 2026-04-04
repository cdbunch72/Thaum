# syntax=docker/dockerfile:1
# Build: docker build -t thaum .
# Buildah: buildah bud -t thaum -f Dockerfile .
#
# Python 3.14: docker build --build-arg PYTHON_VERSION=3.14 -t thaum .

ARG PYTHON_VERSION=3.13

# --- build stage: venv, deps from git + requirements, then strip pip ---
FROM python:${PYTHON_VERSION}-slim AS builder

ARG GEMSTONE_UTILS_REF=main

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        git \
        libffi-dev \
        libssl-dev \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .

RUN python -m venv /venv
ENV PATH="/venv/bin:$PATH"

# Install gemstone_utils from GitHub first; omit the PyPI `gemstone_utils` line from requirements.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        "gemstone_utils[azure] @ git+https://github.com/cdbunch72/gemstone_utils.git@${GEMSTONE_UTILS_REF}" \
    && pip install --no-cache-dir gunicorn \
    && grep -v '^gemstone_utils[[:space:]]*$' requirements.txt > /tmp/requirements.nopypi-eu.txt \
    && pip install --no-cache-dir -r /tmp/requirements.nopypi-eu.txt \
    && pip uninstall -y pip setuptools wheel \
    && rm -f /venv/bin/pip /venv/bin/pip3 /venv/bin/pip3.* 2>/dev/null || true

# --- runtime: copy venv + app only ---
FROM python:${PYTHON_VERSION}-slim AS runtime

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin thaum

WORKDIR /app
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    THAUM_CONFIG_FILE=/etc/thaum/thaum.conf

COPY --from=builder /venv /venv
COPY --chown=1000:1000 . .

USER 1000
VOLUME ["/etc/thaum"]
EXPOSE 5165

# Default 0.0.0.0: reverse proxy (nginx, traefik, host ingress) reaches this container via its
# own IP — not loopback. Binding 127.0.0.1 would drop those connections unless the proxy shares
# this network namespace or uses a Unix socket. Do not publish this port to the public host;
# expose only the proxy. Override for co-located proxy: -e GUNICORN_BIND=127.0.0.1:5165
ENV GUNICORN_BIND=0.0.0.0:5165
# Single worker until leader election coordinates Spark webhook registration / signature secrets
# across processes. Override: -e GUNICORN_WORKERS=4
ENV GUNICORN_WORKERS=1
ENTRYPOINT ["/bin/sh", "-c", "exec /venv/bin/gunicorn --bind \"$GUNICORN_BIND\" --workers \"${GUNICORN_WORKERS:-1}\" app:app"]
