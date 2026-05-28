#!/usr/bin/env sh
# Valida roteamento nginx + API após deploy (rodar na VPS ou com IP em ATS_BASE_URL).
set -eu

BASE="${ATS_BASE_URL:-http://127.0.0.1:8100}"
API_KEY="${ATS_API_KEY:-ats-super-api-key}"

echo "=== AI Token Suppressor — validação de roteamento ==="
echo "BASE_URL=$BASE"
echo ""

echo "1) GET /health/live (JSON liveness)"
curl -sf "$BASE/health/live" | head -c 200
echo ""
echo ""

echo "1b) GET /health → redirect /status; GET /status → HTML SPA"
curl -sfI "$BASE/health" | grep -i '^location:' || true
curl -sf "$BASE/status" | head -c 120 | grep -q '<!DOCTYPE html\|<html' && echo "OK: /status retorna HTML" || echo "FALHA: /status não retorna HTML"
echo ""
echo ""

echo "2) GET /api/health (alias via prefixo /api)"
curl -sf "$BASE/api/health" | head -c 200
echo ""
echo ""

echo "3) GET /v1/models (auth)"
curl -sf "$BASE/v1/models" -H "Authorization: Bearer $API_KEY" | head -c 300
echo ""
echo ""

echo "4) POST /api/compress"
curl -sf "$BASE/api/compress" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"teste"}],"strategy":"fast","use_ollama":false}' \
  | head -c 400
echo ""
echo ""

echo "5) POST /v1/chat/completions"
curl -sf "$BASE/v1/chat/completions" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -H "X-ATS-Strategy: fast" \
  -H "X-ATS-Use-Ollama: false" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"Diga ok"}],"stream":false}' \
  | head -c 500
echo ""
echo ""

echo "=== Concluído ==="
