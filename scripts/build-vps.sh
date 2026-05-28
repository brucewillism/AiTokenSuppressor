#!/usr/bin/env sh
# Build na VPS com rede do host (evita timeout do apt dentro do Docker).
set -eu
cd "$(dirname "$0")/.."

export DOCKER_BUILDKIT=1
export COMPOSE_DOCKER_CLI_BUILD=1

echo "=== Build frontend (nginx + rotas /health) ==="
docker compose build frontend

echo "=== Build API (retentativas apt; pode demorar se a rede estiver lenta) ==="
docker compose build --build-arg BUILDKIT_INLINE_CACHE=1 api

echo "=== Subir serviços ==="
docker compose up -d --force-recreate frontend api

echo "=== Status ==="
docker compose ps

echo ""
echo "Teste: curl -s http://127.0.0.1:8100/health/live"
