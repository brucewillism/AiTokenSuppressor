# VPS com pouca RAM (~4 GB)

## Stack mínimo (recomendado)

Só sobem **redis + api + frontend**. Celery, Flower, LiteLLM, Prometheus e Grafana ficam em profiles opcionais.

```bash
cd /opt/AiTokenSuppressor
git pull

# Parar containers pesados que já existem
docker compose stop celery-worker flower litellm prometheus grafana 2>/dev/null || true
docker compose rm -f celery-worker flower litellm prometheus grafana 2>/dev/null || true

# Subir só o essencial
docker compose up -d --build redis api frontend
```

Profiles opcionais (só se tiver RAM):

```bash
docker compose --profile workers up -d      # celery + flower
docker compose --profile monitoring up -d   # prometheus + grafana
docker compose --profile litellm up -d      # gateway LiteLLM
```

## `.env` na VPS — valores seguros

```env
PROXY_DEFAULT_STRATEGY=fast
PROXY_USE_OLLAMA=false
PROXY_USE_MEMORY=false
DATABASE_POOL_SIZE=5
DATABASE_MAX_OVERFLOW=3
```

**Evite** `PROXY_DEFAULT_STRATEGY=ultra` + `PROXY_USE_OLLAMA=true` na mesma VPS: cada request do Claude Code dispara compressão pesada + modelo local.

Valores com espaço no `.env` precisam de aspas (ex.: `APP_NAME="AI Token Suppressor"`) — senão o Docker Compose falha com `key cannot contain a space`.

O endpoint `/v1/messages` (Claude Code) **ignora** ollama/memória do `.env` salvo header explícito `X-ATS-Use-Ollama` / `X-ATS-Use-Memory`.

## Qualidade sem estourar RAM

O supressor usa **estratégia automática por tamanho** (sem Ollama):

| Tokens do prompt | Estratégia | Economia | RAM |
|------------------|------------|----------|-----|
| &lt; 400 | `fast` | leve | mínima |
| 400–800+ com código | `code-focused` | alta em código | baixa |
| 800+ geral | `balanced` | alta (dedup + specialized) | baixa |
| `ultra` no .env sem Ollama | vira `balanced` | quase igual, sem modelo local | **muito menor** |

Cache Redis (128 MB, LRU) acelera requests repetidos — **melhora desempenho** sem perder qualidade.

```env
LOW_MEMORY_MODE=true
PROMETHEUS_ENABLED=false
COMPRESS_AUTO_BALANCED_TOKENS=800
```

Para forçar `ultra` + Ollama (máxima economia, **muita RAM**): header `X-ATS-Strategy: ultra` + `X-ATS-Use-Ollama: true`.

## Ollama no host

Se Ollama roda fora do Docker na porta 11999:

```bash
sudo systemctl stop ollama   # ou kill do processo
free -h
```

## Recuperação rápida (memória cheia / swap 100%)

```bash
docker compose stop celery-worker flower litellm prometheus grafana
docker stats --no-stream
free -h
docker compose up -d --force-recreate api frontend
```

## ConsumoEsperto

`/api/optimize` ainda respeita o `.env`. Para economia de RAM no gateway Java, use estratégia `fast` ou `balanced` e `use_ollama: false` no body.
