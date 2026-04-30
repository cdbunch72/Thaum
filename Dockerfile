# syntax=docker/dockerfile:1
# Build (base image): docker build -t localhost/thaum:local .
# Build (azure-enabled variant): docker build --build-arg THAUM_ENABLE_AZURE=1 -t localhost/thaum-azure:local .
# Buildah: buildah bud -t localhost/thaum:local -f Dockerfile .
#
# Python 3.14: docker build --build-arg PYTHON_VERSION=3.14 -t localhost/thaum:local .
#
# Bundled PostgreSQL (default): unset THAUM_EXTERNAL_DB or false; app connects via Unix socket (peer).
# External DB: THAUM_EXTERNAL_DB=true and set [server.database].db_url — entrypoint runs gunicorn only.

ARG PYTHON_VERSION=3.13

# --- build stage: venv, deps from git + requirements, then strip pip ---
FROM python:${PYTHON_VERSION}-slim AS builder

ARG GEMSTONE_UTILS_REF=v0.4.0rc1
ARG THAUM_ENABLE_AZURE=0

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

# Install gemstone_utils from GitHub first; omit any gemstone_utils requirement line from requirements.txt.
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && if [ "${THAUM_ENABLE_AZURE}" = "1" ]; then \
         GEMSTONE_SPEC="gemstone_utils[azure] @ git+https://github.com/gemstone-software-dev/gemstone_utils.git@${GEMSTONE_UTILS_REF}"; \
       else \
         GEMSTONE_SPEC="gemstone_utils @ git+https://github.com/gemstone-software-dev/gemstone_utils.git@${GEMSTONE_UTILS_REF}"; \
       fi \
    && pip install --no-cache-dir "${GEMSTONE_SPEC}" \
    && grep -v '^gemstone_utils' requirements.txt > /tmp/requirements.nopypi-eu.txt \
    && pip install --no-cache-dir -r /tmp/requirements.nopypi-eu.txt \
    && pip uninstall -y pip setuptools wheel \
    && rm -f /venv/bin/pip /venv/bin/pip3 /venv/bin/pip3.* 2>/dev/null || true

# --- runtime: copy venv + app only ---
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG THAUM_IMAGE_VERSION=unknown
ARG THAUM_IMAGE_CHANNEL=local
LABEL org.opencontainers.image.version="${THAUM_IMAGE_VERSION}" \
      thaum.image.channel="${THAUM_IMAGE_CHANNEL}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gosu \
        postgresql \
        postgresql-client \
        supervisor \
    && rm -rf /var/lib/apt/lists/* \
    && PG_BINDIR="$(ls -d /usr/lib/postgresql/*/bin | head -n1)" \
    && for f in initdb pg_ctl postgres pg_isready; do \
        ln -sf "${PG_BINDIR}/${f}" "/usr/local/bin/${f}"; \
    done

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin thaum \
    && usermod -aG postgres thaum

WORKDIR /app
# Do not set THAUM_CONFIG_FILE in the image. Let runtime configuration decide config location.
# Prefer .toml over .conf for the same TOML content for better editor syntax highlighting.
ENV PATH="/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --from=builder /venv /venv
COPY --chown=1000:1000 . .

COPY docker/supervisord.conf /etc/supervisor/supervisord.conf

RUN chmod +x \
        /app/docker/entrypoint.sh \
        /app/docker/wait_for_pg.sh \
        /app/docker/run_thaum.sh \
        /app/docker/pg_bootstrap.py

USER root
VOLUME ["/etc/thaum", "/var/lib/thaum"]
EXPOSE 5165

# Default 0.0.0.0: reverse proxy reaches this container via its own IP.
# Do not publish this port to the public host; expose only the proxy.
ENV GUNICORN_BIND=0.0.0.0:5165
ENV GUNICORN_WORKERS=1

ENTRYPOINT ["/app/docker/entrypoint.sh"]
