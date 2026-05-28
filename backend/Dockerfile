# Estágio 1: dependências Python (gcc só aqui; wheels quando possível)
FROM python:3.12-slim-bookworm AS builder

WORKDIR /app

# Retentativas para VPS com rede instável ao deb.debian.org
RUN set -eux; \
    apt_install() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"; \
    }; \
    for i in 1 2 3 4 5; do \
      apt_install gcc libpq-dev && break; \
      echo "apt-get falhou (tentativa ${i}/5), aguardando..."; \
      sleep 15; \
    done; \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt

# Estágio 2: imagem final enxuta (sem gcc; healthcheck via Python)
FROM python:3.12-slim-bookworm

WORKDIR /app

# libpq5 em runtime (asyncpg); falha de rede não aborta o build
RUN set -eux; \
    apt_install() { \
      apt-get update && \
      DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"; \
    }; \
    for i in 1 2 3; do \
      apt_install libpq5 && break; \
      echo "libpq5 opcional falhou (tentativa ${i}/3)"; \
      sleep 10; \
    done; \
    rm -rf /var/lib/apt/lists/* || true

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN chmod +x docker-entrypoint.sh

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5)"

ENTRYPOINT ["./docker-entrypoint.sh"]
